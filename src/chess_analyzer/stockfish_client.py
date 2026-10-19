"""Local Stockfish subprocess management using python-chess's UCI transport."""

import os
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from time import perf_counter
from types import TracebackType

import chess
import chess.engine

from chess_analyzer.config import Settings
from chess_analyzer.models import PositionEvaluation, StockfishEngineError


@dataclass(frozen=True, slots=True)
class EngineStatistics:
    """Cumulative searches attempted and wall time spent searching (not startup)."""

    positions: int
    search_seconds: float


def resolve_stockfish_path(configured: str | None = None) -> str:
    """Find an executable without downloading anything or invoking a shell.

    An explicitly configured executable never silently falls back to another.
    Raises StockfishEngineError with installation guidance if none is executable.
    """
    candidates = (
        [configured]
        if configured is not None
        else ["stockfish", "/usr/games/stockfish", "/usr/bin/stockfish"]
    )
    for candidate in candidates:
        executable = which(str(Path(candidate).expanduser()))
        if executable and Path(executable).is_file() and os.access(executable, os.X_OK):
            return executable
    raise StockfishEngineError(
        "Stockfish executable not found or not executable. On Ubuntu/Debian run "
        "'sudo apt-get update && sudo apt-get install -y stockfish', or set "
        "STOCKFISH_PATH to a trusted executable (often /usr/games/stockfish)."
    )


def terminal_evaluation(board: chess.Board) -> PositionEvaluation | None:
    """Score automatic game ends locally, retaining any available board history.

    Claimable threefold/fifty-move draws are not assumed to have been claimed.
    """
    outcome = board.outcome(claim_draw=False)
    if outcome is None:
        return None
    if outcome.winner is not None:
        return PositionEvaluation(mate=0, terminal_result=outcome.result())
    return PositionEvaluation(cp=0, terminal_result=outcome.result())


class StockfishClient:
    """Evaluate standard or Chess960 positions with one reusable UCI process.

    Args:
        settings: Validated engine path, search limits, and resource limits.

    Startup is lazy: entering the context or the first nonterminal evaluation
    starts the engine. Always use a context manager or call close(). Batches run
    sequentially on this same process, retaining its hash table. Configure engine
    threads rather than parallel HTTP workers. Public methods must not be called
    concurrently on the same client. A closed/failed client cannot be reused.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine: chess.engine.SimpleEngine | None = None
        self._closed = False
        self._positions = 0
        self._search_seconds = 0.0

    def __enter__(self) -> "StockfishClient":
        self._start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _check_open(self) -> None:
        if self._closed:
            raise StockfishEngineError(
                "Stockfish client is closed; create a new client."
            )

    def _start(self) -> chess.engine.SimpleEngine:
        self._check_open()
        if self._engine is None:
            try:
                executable = resolve_stockfish_path(self.settings.stockfish_path)
                # A list treats paths with spaces as one executable, never a command.
                self._engine = chess.engine.SimpleEngine.popen_uci(
                    [executable], timeout=self.settings.engine_timeout_seconds
                )
                self._engine.configure(
                    {"Threads": self.settings.threads, "Hash": self.settings.hash_mb}
                )
            except (OSError, TimeoutError, chess.engine.EngineError) as error:
                self.close()
                raise StockfishEngineError(
                    "Unable to start/configure Stockfish. Check STOCKFISH_PATH, "
                    "engine compatibility, thread/hash limits, and timeout."
                ) from error
            except BaseException:
                self.close()
                raise
        return self._engine

    def close(self) -> None:
        """Idempotently quit the owned engine; force transport cleanup if needed.

        Shutdown failures from a dead/unresponsive engine are handled by closing
        its transport so they do not mask the original analysis error.
        """
        self._closed = True
        engine, self._engine = self._engine, None
        if engine is not None:
            try:
                engine.quit()
            except (OSError, TimeoutError, chess.engine.EngineError):
                pass  # Forced cleanup below also covers a crashed or hung engine.
            finally:
                engine.close()

    @property
    def statistics(self) -> EngineStatistics:
        """Return attempted search count and elapsed search time, even on failure."""
        return EngineStatistics(self._positions, self._search_seconds)

    @staticmethod
    def _board(fen: str, *, chess960: bool = False) -> chess.Board:
        board = chess.Board(fen, chess960=chess960)
        if not board.is_valid():
            raise ValueError("FEN must describe a valid position for the chosen rules.")
        return board

    def evaluate_many(
        self, fens: list[str], *, chess960: bool = False
    ) -> list[PositionEvaluation]:
        """Validate all FENs first, then search in input order on the same engine.

        Empty/terminal-only batches need no engine. Failure raises immediately;
        no partial batch is returned and subsequent positions are not searched.
        Set chess960=True for every position in a Chess960 batch.
        """
        self._check_open()
        boards = [self._board(fen, chess960=chess960) for fen in fens]
        return [self._evaluate_board(board) for board in boards]

    def evaluate(self, fen: str, *, chess960: bool = False) -> PositionEvaluation:
        """Return White-relative centipawns/mate and a legal best move for a FEN.

        Terminal boards are scored locally. FENs cannot convey repetition history.
        Search stops at the first of the configured depth/time limits. The time
        limit is an engine search budget, not an exact total wall-time guarantee.
        Set chess960=True for Chess960; FEN alone does not identify the variant.
        python-chess automatically manages the engine's UCI_Chess960 option.

        Raises:
            ValueError: The FEN is invalid.
            StockfishEngineError: Startup, protocol, timeout, or result failure.
        """
        self._check_open()
        return self._evaluate_board(self._board(fen, chess960=chess960))

    def _evaluate_board(self, board: chess.Board) -> PositionEvaluation:
        terminal = terminal_evaluation(board)
        if terminal is not None:
            return terminal
        engine = self._start()
        started = perf_counter()
        self._positions += 1
        try:
            info = engine.analyse(
                board,
                chess.engine.Limit(
                    depth=self.settings.analysis_depth,
                    time=self.settings.analysis_time_seconds,
                ),
                info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
            )
            return self._parse_evaluation(info, board)
        except (OSError, TimeoutError, chess.engine.EngineError) as error:
            self.close()
            raise StockfishEngineError(
                "Stockfish analysis failed or timed out; the engine has been closed. "
                "Check available resources and STOCKFISH_TIMEOUT_SECONDS."
            ) from error
        except BaseException:
            self.close()
            raise
        finally:
            self._search_seconds += perf_counter() - started

    @staticmethod
    def _parse_evaluation(
        info: chess.engine.InfoDict, board: chess.Board
    ) -> PositionEvaluation:
        pov = info.get("score")
        pv = info.get("pv", [])
        if not isinstance(pov, chess.engine.PovScore):
            raise StockfishEngineError("Stockfish returned no valid score.")
        if not pv or pv[0] not in board.legal_moves:
            raise StockfishEngineError("Stockfish returned no legal best move.")
        score = pov.white()
        if score.is_mate():
            mate = score.mate()
            if mate is None or mate == 0:
                raise StockfishEngineError("Stockfish returned an invalid mate score.")
            return PositionEvaluation(mate=mate, best_move_uci=pv[0].uci())
        cp = score.score()
        if cp is None:
            raise StockfishEngineError("Stockfish returned no centipawn score.")
        return PositionEvaluation(cp=cp, best_move_uci=pv[0].uci())
