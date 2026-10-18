"""Stockfish Online transport, isolated from PGN replay and configuration I/O."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import TracebackType

import chess
import requests

from chess_analyzer.config import Settings
from chess_analyzer.models import PositionEvaluation, StockfishAPIError


def terminal_evaluation(board: chess.Board) -> PositionEvaluation | None:
    """Return local automatic-game-end scores, retaining board history.

    Claimable threefold/fifty-move draws are not assumed to have been claimed.
    """
    outcome = board.outcome(claim_draw=False)
    if outcome is None:
        return None
    if outcome.winner is not None:
        return PositionEvaluation(mate=0, terminal_result=outcome.result())
    return PositionEvaluation(cp=0, terminal_result=outcome.result())


class StockfishOnlineClient:
    """Synchronous authenticated provider client using shared Settings.

    Numeric provider evaluations are interpreted as White-relative pawn units.
    The API documentation explicitly defines the mate sign but is less explicit
    about numeric perspective/units; live verification is recommended.

    Args:
        settings: Validated, centrally loaded application configuration.
        session: Optional reusable session owned and closed by the caller.

    Use as a context manager or call close() to close an internally owned session.
    Instances are not intended for concurrent use across threads.
    """

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None

    def __enter__(self) -> "StockfishOnlineClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close only an internally owned HTTP session."""
        if self._owns_session:
            self._session.close()

    def evaluate(self, fen: str) -> PositionEvaluation:
        """Evaluate a standard-chess FEN or resolve a terminal board locally.

        Args:
            fen: A valid standard-chess FEN. Repetition history is unavailable.

        Returns:
            White-relative score and legal best move (unless terminal).

        Raises:
            ValueError: The FEN is invalid.
            StockfishAPIError: HTTP, provider, or response validation fails.

        Nonterminal positions are sent to the provider over HTTPS with the API
        key in the query. Redirects and automatic retries are not enabled.
        """
        board = chess.Board(fen)
        if not board.is_valid():
            raise ValueError("FEN must describe a valid standard-chess position.")
        terminal = terminal_evaluation(board)
        if terminal is not None:
            return terminal
        try:
            response = self._session.get(
                self.settings.stockfish_api_url,
                params={
                    "fen": fen,
                    "depth": self.settings.analysis_depth,
                    "key": self.settings.stockfish_api_key,
                },
                timeout=self.settings.request_timeout_seconds,
                allow_redirects=False,
            )
        except requests.Timeout:
            raise StockfishAPIError("Stockfish request timed out.") from None
        except requests.RequestException:
            # Request exceptions commonly include the credential-bearing URL.
            raise StockfishAPIError("Unable to contact Stockfish Online.") from None
        try:
            if not 200 <= response.status_code < 300:
                raise StockfishAPIError(
                    f"Stockfish Online returned HTTP {response.status_code}."
                )
            try:
                payload = response.json()
            except ValueError:
                raise StockfishAPIError("Stockfish returned invalid JSON.") from None
            return self._parse_evaluation(payload, board)
        finally:
            response.close()

    @staticmethod
    def _parse_evaluation(payload: object, board: chess.Board) -> PositionEvaluation:
        if not isinstance(payload, dict):
            raise StockfishAPIError("Stockfish returned an invalid response object.")
        if payload.get("success") is not True:
            # Do not echo provider error bodies, which may contain request URLs.
            raise StockfishAPIError("Stockfish Online did not complete the analysis.")
        raw_move = payload.get("bestmove")
        if not isinstance(raw_move, str):
            raise StockfishAPIError("Stockfish response has no best move.")
        parts = raw_move.split()
        if len(parts) < 2 or parts[0] != "bestmove":
            raise StockfishAPIError("Stockfish returned an invalid best move.")
        try:
            best_move = chess.Move.from_uci(parts[1])
        except ValueError:
            raise StockfishAPIError(
                "Stockfish returned an invalid best move."
            ) from None
        if best_move not in board.legal_moves:
            raise StockfishAPIError("Stockfish returned an illegal best move.")

        # Documentation prose uses 'eval'; the documented response uses 'evaluation'.
        evaluation = payload.get("evaluation", payload.get("eval"))
        mate = payload.get("mate")
        if mate is not None:
            if type(mate) is not int or mate == 0 or evaluation is not None:
                raise StockfishAPIError("Stockfish returned an invalid mate score.")
            return PositionEvaluation(mate=mate, best_move_uci=best_move.uci())
        if isinstance(evaluation, bool) or not isinstance(evaluation, (int, float)):
            raise StockfishAPIError("Stockfish response has no valid numeric score.")
        try:
            pawn_score = Decimal(str(evaluation))
            if not pawn_score.is_finite():
                raise InvalidOperation
            cp = int((pawn_score * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError, OverflowError):
            raise StockfishAPIError(
                "Stockfish returned an invalid numeric score."
            ) from None
        return PositionEvaluation(cp=cp, best_move_uci=best_move.uci())
