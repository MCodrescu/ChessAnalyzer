"""Typed results and errors for position and game analysis."""

from dataclasses import dataclass
from typing import Literal


class StockfishAPIError(RuntimeError):
    """The provider request or response failed; messages exclude credentials."""


class InvalidPGNError(ValueError):
    """Input does not describe one supported, legally replayable chess game."""


@dataclass(frozen=True, slots=True)
class PositionEvaluation:
    """White-relative centipawns or signed mate distance, never both.

    Positive scores favor White. Mate zero denotes checkmate; terminal_result
    identifies the winner in that case. best_move_uci is absent for terminal
    positions. Draws have cp=0. No artificial centipawn value represents mate.
    """

    cp: int | None = None
    mate: int | None = None
    best_move_uci: str | None = None
    terminal_result: str | None = None

    def __post_init__(self) -> None:
        if (self.cp is None) == (self.mate is None):
            raise ValueError("An evaluation must contain exactly one of cp or mate.")
        score = self.cp if self.cp is not None else self.mate
        if type(score) is not int:
            raise ValueError("Evaluation scores must be integers.")


@dataclass(frozen=True, slots=True)
class MoveAnalysis:
    """One mainline move and its estimated quality.

    ply counts from one within the supplied game; fullmove_number respects its
    starting FEN. Scores remain White-relative; cp_delta is loss from the moving
    player's perspective and can be negative because of search noise. Mate
    transitions have cp_delta and estimated_cp_loss set to None.
    """

    ply: int
    fullmove_number: int
    player: Literal["white", "black"]
    fen_before: str
    fen_after: str
    played_move_uci: str
    played_move_san: str
    best_move_uci: str
    best_move_san: str
    evaluation_before: PositionEvaluation
    evaluation_after: PositionEvaluation
    cp_delta: int | None
    estimated_cp_loss: int | None
    is_best_move: bool


@dataclass(frozen=True, slots=True)
class GameAnalysis:
    """PGN headers, ordered mainline results, and the search depth used."""

    headers: dict[str, str]
    moves: tuple[MoveAnalysis, ...]
    analysis_depth: int
