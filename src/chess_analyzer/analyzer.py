"""PGN validation, mainline replay, and moving-player loss estimation."""

from io import StringIO
from typing import Protocol, runtime_checkable

import chess
import chess.pgn

from chess_analyzer.config import Settings
from chess_analyzer.models import (
    GameAnalysis,
    InvalidPGNError,
    MoveAnalysis,
    PositionEvaluation,
    StockfishEngineError,
)
from chess_analyzer.stockfish_client import terminal_evaluation


class PositionEvaluator(Protocol):
    """Minimal evaluator contract for injection and deterministic tests."""

    settings: Settings

    def evaluate(self, fen: str) -> PositionEvaluation:
        """Return a White-relative score and best move for the given FEN."""
        ...


@runtime_checkable
class BatchPositionEvaluator(Protocol):
    """Optional ordered-batch capability for position evaluators."""

    def evaluate_many(self, fens: list[str]) -> list[PositionEvaluation]:
        """Return one evaluation per FEN, in the same order as the input."""
        ...


class _GameBuilder(chess.pgn.GameBuilder):
    def __init__(self) -> None:
        super().__init__()
        self._has_headers_or_result = False

    def visit_header(self, tagname: str, tagvalue: str) -> None:
        self._has_headers_or_result = True
        super().visit_header(tagname, tagvalue)

    def visit_result(self, result: str) -> None:
        self._has_headers_or_result = True
        super().visit_result(result)

    def result(self) -> chess.pgn.Game:
        game = super().result()
        # The forgiving parser can turn unrelated text into an empty game.
        if not game.variations and not self._has_headers_or_result:
            raise InvalidPGNError("PGN does not contain a game.")
        return game

    def handle_error(self, error: Exception) -> None:
        # Raise immediately rather than log input and silently analyze a prefix.
        raise InvalidPGNError("PGN contains an invalid position or move.") from None


class PGNAnalyzer:
    """Analyze both players' mainline moves using an injected evaluator.

    Args:
        client: Position evaluator configured with centralized Settings.
    """

    def __init__(self, client: PositionEvaluator):
        self._client = client

    def analyze(self, pgn: str) -> GameAnalysis:
        """Validate one game, then return its ordered move-quality estimates.

        Supports standard chess including SetUp/FEN starts. Comments and side
        variations do not contribute moves. Valid games without moves return an
        empty result. Validation/replay completes before any engine searches.

        Raises:
            InvalidPGNError: Input is empty, has multiple games, is an unsupported
                variant, or cannot be legally replayed to its end.
            StockfishEngineError: Evaluation fails or returns an invalid best move.

        Makes at most n+1 evaluations for n moves, skipping local terminal boards.
        Uses ordered batch evaluation when supported by the injected evaluator.
        A failure raises rather than returning a misleading partial result.
        """
        game, board = self._parse_game(pgn)
        moves = tuple(game.mainline_moves())
        results: list[MoveAnalysis] = []
        evaluations = (
            self._evaluate_batch(board, moves)
            if moves and isinstance(self._client, BatchPositionEvaluator)
            else None
        )
        before = (
            evaluations[0]
            if evaluations is not None
            else self._evaluate(board)
            if moves
            else None
        )
        for ply, move in enumerate(moves, start=1):
            assert before is not None
            best_move = self._best_move(before, board)
            fen_before = board.fen()
            player = board.turn
            fullmove_number = board.fullmove_number
            played_san = board.san(move)
            best_san = board.san(best_move)
            board.push(move)
            after = (
                evaluations[ply] if evaluations is not None else self._evaluate(board)
            )
            is_best = move == best_move
            delta = None
            loss = None
            if before.cp is not None and after.cp is not None:
                delta = (before.cp - after.cp) * (1 if player == chess.WHITE else -1)
                loss = 0 if is_best else max(0, delta)
            results.append(
                MoveAnalysis(
                    ply=ply,
                    fullmove_number=fullmove_number,
                    player="white" if player else "black",
                    fen_before=fen_before,
                    fen_after=board.fen(),
                    played_move_uci=move.uci(),
                    played_move_san=played_san,
                    best_move_uci=best_move.uci(),
                    best_move_san=best_san,
                    evaluation_before=before,
                    evaluation_after=after,
                    cp_delta=delta,
                    estimated_cp_loss=loss,
                    is_best_move=is_best,
                )
            )
            before = after
        return GameAnalysis(
            headers=dict(game.headers),
            moves=tuple(results),
            analysis_depth=self._client.settings.analysis_depth,
            analysis_time_seconds=self._client.settings.analysis_time_seconds,
        )

    def _evaluate_batch(
        self, board: chess.Board, moves: tuple[chess.Move, ...]
    ) -> list[PositionEvaluation]:
        """Collect positions first, retaining history for automatic draw detection."""
        assert isinstance(self._client, BatchPositionEvaluator)
        replay = board.copy()
        fens = []
        positions = []
        local: list[PositionEvaluation | None] = []
        for index in range(len(moves) + 1):
            terminal = terminal_evaluation(replay)
            local.append(terminal)
            if terminal is None:
                positions.append(index)
                fens.append(replay.fen())
            if index < len(moves):
                replay.push(moves[index])
        evaluated = self._client.evaluate_many(fens) if fens else []
        if len(evaluated) != len(fens):
            raise StockfishEngineError(
                "Evaluator returned an incomplete position batch."
            )
        for index, evaluation in zip(positions, evaluated, strict=True):
            local[index] = evaluation
        return [evaluation for evaluation in local if evaluation is not None]

    def _evaluate(self, board: chess.Board) -> PositionEvaluation:
        # Preserve history-dependent automatic draws before reducing to a FEN.
        terminal = terminal_evaluation(board)
        return terminal if terminal is not None else self._client.evaluate(board.fen())

    @staticmethod
    def _best_move(evaluation: PositionEvaluation, board: chess.Board) -> chess.Move:
        try:
            move = chess.Move.from_uci(evaluation.best_move_uci or "")
        except ValueError:
            raise StockfishEngineError(
                "Evaluator returned an invalid best move."
            ) from None
        if move not in board.legal_moves:
            raise StockfishEngineError("Evaluator returned an illegal best move.")
        return move

    @staticmethod
    def parse_game(pgn: str) -> tuple[chess.pgn.Game, chess.Board]:
        """Validate one standard PGN without starting an engine.

        Return the parsed game and starting board. Raise InvalidPGNError for
        unsupported variants, invalid positions, illegal moves, or extra games.
        Web callers can enforce move-count limits before allocating an engine.
        """
        return PGNAnalyzer._parse_game(pgn)

    @staticmethod
    def _parse_game(pgn: str) -> tuple[chess.pgn.Game, chess.Board]:
        if not isinstance(pgn, str) or not pgn.strip():
            raise InvalidPGNError("Provide a nonempty PGN string containing one game.")
        stream = StringIO(pgn)
        try:
            game = chess.pgn.read_game(stream, Visitor=_GameBuilder)
            if game is None:
                raise InvalidPGNError("PGN does not contain a game.")
            if chess.pgn.read_game(stream, Visitor=_GameBuilder) is not None:
                raise InvalidPGNError("Provide exactly one PGN game.")
            board = game.board()
        except ValueError as error:
            if isinstance(error, InvalidPGNError):
                raise
            raise InvalidPGNError(
                "PGN contains an invalid starting position."
            ) from None
        if type(board) is not chess.Board or board.chess960:
            raise InvalidPGNError("Only standard chess is supported.")
        if not board.is_valid():
            raise InvalidPGNError("PGN contains an invalid starting position.")
        replay = board.copy()
        for move in game.mainline_moves():
            if replay.is_game_over(claim_draw=False):
                raise InvalidPGNError("PGN contains moves after automatic game end.")
            if move not in replay.legal_moves:
                raise InvalidPGNError("PGN contains an illegal mainline move.")
            replay.push(move)
        return game, board
