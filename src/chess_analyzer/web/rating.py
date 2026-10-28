"""Validate rating eligibility without loading models or starting an engine."""

import math
import re

from chess_analyzer.analyzer import PGNAnalyzer
from chess_analyzer.models import InvalidPGNError
from chess_analyzer.web.services import MAX_PGN_CHARACTERS, MAX_PLIES


def validate_rating_pgn(pgn: str) -> str:
    """Reject games outside the trained model's supported input domain.

    Args:
        pgn: Original PGN including clock annotations and time-control headers.

    Returns:
        The supported time category; invalid input raises InvalidPGNError.
    """
    if not isinstance(pgn, str) or len(pgn) > MAX_PGN_CHARACTERS:
        raise InvalidPGNError("Provide a PGN of at most 100,000 characters.")
    game, board = PGNAnalyzer.parse_game(pgn)
    if board.chess960 or board.uci_variant != "chess":
        raise InvalidPGNError("Performance ratings require standard chess.")
    nodes = list(game.mainline())
    if not 2 <= len(nodes) <= MAX_PLIES:
        raise InvalidPGNError("Performance ratings require moves by both players.")
    if game.headers.get("Result") not in {"1-0", "0-1", "1/2-1/2"}:
        raise InvalidPGNError("Performance ratings require a completed game.")
    control = re.fullmatch(
        r"(\d{1,8})(?:\+(\d{1,8}))?", game.headers.get("TimeControl", "")
    )
    if not control or int(control[1]) <= 0:
        raise InvalidPGNError("Performance ratings require a live time control.")
    duration = int(control[1]) + 40 * int(control[2] or 0)
    if duration >= 3600:
        raise InvalidPGNError(
            "Performance ratings support bullet, blitz, and rapid only."
        )
    clocks = [node.clock() for node in nodes]
    if any(clock is None or not math.isfinite(clock) or clock < 0 for clock in clocks):
        raise InvalidPGNError(
            "Performance ratings require valid clock annotations on every move."
        )
    if duration < 180:
        return "bullet"
    if duration < 600:
        return "blitz"
    return "rapid"
