"""Build the existing game review from the rating model's position analysis."""

import logging
from dataclasses import asdict
from importlib import import_module

import chess
from django.conf import settings

from chess_analyzer.analyzer import PGNAnalyzer
from chess_analyzer.config import Settings
from chess_analyzer.models import (
    InvalidPGNError,
    PositionEvaluation,
    StockfishEngineError,
)
from chess_analyzer.stockfish_client import terminal_evaluation
from chess_analyzer.web.rating import validate_rating_pgn
from chess_analyzer.web.services import analyze_pgn

logger = logging.getLogger(__name__)


class PrecomputedEvaluator:
    """Adapt ordered model evaluations without allocating another engine."""

    def __init__(self, pgn: str, positions: list[dict], engine_settings: dict):
        """Validate reached boards and translate their White-relative scores.

        Args:
            pgn: Original game, preserving its initial position and history.
            positions: Model analysis dictionaries in chronological board order.
            engine_settings: Search settings recorded by the model's analyzer.

        Returns:
            None; mismatched or incomplete analysis raises StockfishEngineError.
        """
        self.settings = Settings(
            analysis_depth=engine_settings["depth"],
            analysis_time_seconds=None,
            threads=engine_settings["threads"],
            hash_mb=engine_settings["hash_mb"],
        )
        game, board = PGNAnalyzer.parse_game(pgn)
        moves = tuple(game.mainline_moves())
        if len(positions) != len(moves) + 1:
            raise StockfishEngineError("Shared analysis has incomplete positions.")
        self.evaluations = []
        self.fens = []
        for index, position in enumerate(positions):
            if position["fen"] != board.fen():
                raise StockfishEngineError("Shared analysis does not match the game.")
            if terminal_evaluation(board) is None:
                candidates = position["candidates"]
                if not candidates:
                    raise StockfishEngineError(
                        "Shared analysis has no candidate moves."
                    )
                score = position.get("evaluation") or candidates[0]["score"]
                self.fens.append(board.fen())
                self.evaluations.append(
                    PositionEvaluation(
                        cp=int(score["cp"]) if score.get("cp") is not None else None,
                        mate=score.get("mate"),
                        best_move_uci=candidates[0]["move"],
                    )
                )
            if index < len(moves):
                board.push(moves[index])

    def evaluate_many(self, fens: list[str], *, chess960: bool = False):
        """Return the already computed scores for the exact requested sequence.

        Args:
            fens: Ordered nonterminal positions requested by PGNAnalyzer.
            chess960: Must be false for the standard-chess rating contract.

        Returns:
            Position evaluations without engine calls.
        """
        if chess960 or fens != self.fens:
            raise StockfishEngineError("Shared analysis position sequence differs.")
        return self.evaluations

    def evaluate(self, fen: str, *, chess960: bool = False):
        """Reject individual lookups that could lose repetition-history alignment.

        Args:
            fen: Requested board position.
            chess960: Requested variant.

        Returns:
            Never; shared analysis requires an ordered batch.
        """
        raise StockfishEngineError("Shared analysis requires ordered batch evaluation.")


def review_from_positions(
    pgn: str, positions: list[dict], engine_settings: dict
) -> dict:
    """Build the board-review response exclusively from supplied model analysis.

    Args:
        pgn: Original validated game.
        positions: Chronological model analysis, including the final position.
        engine_settings: Actual analysis settings used for those evaluations.

    Returns:
        The existing review payload, suitable for accuracy and graph calculations.
    """
    evaluator = PrecomputedEvaluator(pgn, positions, engine_settings)
    result = PGNAnalyzer(evaluator).analyze(pgn)
    _, initial_board = PGNAnalyzer.parse_game(pgn)
    payload = asdict(result)
    payload["initial_fen"] = initial_board.fen()
    for move in payload["moves"]:
        board = chess.Board(move["fen_before"])
        board.push_uci(move["best_move_uci"])
        move["best_fen"] = board.fen()
    return payload


class SharedGameAnalyzer:
    """Analyze a game once and reuse the positions for review and rating."""

    def __init__(self):
        """Defer model loading until an eligible game is requested.

        Args:
            None.

        Returns:
            None.
        """
        self.estimator = None

    def _load_estimator(self):
        """Load the trusted model without starting a Stockfish analysis.

        Args:
            None.

        Returns:
            A reusable estimator configured for the deployed model and engine.
        """
        config = import_module("elo_model.config").InferenceConfig(
            model_directory=settings.RATING_MODEL_DIRECTORY,
            engine_executable=settings.RATING_STOCKFISH_EXECUTABLE,
            cache_directory=settings.RATING_ANALYSIS_CACHE,
            engine_compatibility=settings.RATING_ENGINE_COMPATIBILITY,
        )
        return import_module("elo_model.inference").RatingEstimator(config)

    def analyze(self, pgn: str) -> tuple[dict, dict | None, str | None]:
        """Run one engine pipeline, then build review and rating from its output.

        Args:
            pgn: Validated original game including clock annotations.

        Returns:
            Review, optional rating, and a user-safe rating-unavailability reason.
        """
        try:
            validate_rating_pgn(pgn)
        except InvalidPGNError as error:
            return analyze_pgn(pgn), None, str(error)
        if self.estimator is None:
            self.estimator = self._load_estimator()
        analysis_api = import_module("elo_model.analysis")
        game = import_module("elo_model.game").GameInput.from_pgn(pgn)
        engine_config = import_module("elo_model.config").EngineConfig(
            executable=settings.RATING_STOCKFISH_EXECUTABLE,
            **self.estimator.predictor.manifest["engine"]["settings"],
        )
        with analysis_api.StockfishAnalyzer(
            engine_config,
            analysis_api.AnalysisCache(settings.RATING_ANALYSIS_CACHE),
        ) as analyzer:
            self.estimator.predictor.validate_engine_metadata(
                analyzer.metadata,
                engine_compatibility=settings.RATING_ENGINE_COMPATIBILITY,
            )
            analysis_key, positions = analyzer.analyze(game)
            metadata = analyzer.metadata
            cache_hit = analyzer.cache_hits > 0
        review = review_from_positions(
            pgn,
            [asdict(position) for position in positions],
            metadata["settings"],
        )
        try:
            estimate = self.estimator.predict_pgn(
                pgn,
                analysis=positions,
                engine_metadata=metadata,
            ).model_dump(mode="json")
        except Exception:
            logger.exception("Rating prediction failed after shared game analysis")
            return review, None, "Performance rating unavailable for this analysis."
        estimate["analysis_key"] = analysis_key
        estimate["cache_hit"] = cache_hit
        return review, estimate, None
