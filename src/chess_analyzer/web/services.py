"""Adapt engine results to a board-review payload without persisting PGNs."""

from dataclasses import asdict

import chess

from chess_analyzer.analyzer import PGNAnalyzer
from chess_analyzer.config import load_settings
from chess_analyzer.models import InvalidPGNError
from chess_analyzer.stockfish_client import StockfishClient

MAX_PLIES = 600
MAX_PGN_CHARACTERS = 100_000


def analyze_pgn(pgn: str) -> dict:
    """Return serializable analysis and legal best-move preview positions.

    Validate the PGN and enforce limits before allocating a local engine. Each
    call owns its client and always closes it, including on analysis failure.
    Empty games need no engine. Scores retain the analyzer's White perspective.
    """
    if not isinstance(pgn, str) or len(pgn) > MAX_PGN_CHARACTERS:
        raise InvalidPGNError("Provide a PGN of at most 100,000 characters.")
    game, initial_board = PGNAnalyzer.parse_game(pgn)
    if sum(1 for _ in game.mainline_moves()) > MAX_PLIES:
        raise InvalidPGNError(f"Games may contain at most {MAX_PLIES} half-moves.")
    # Startup remains lazy so empty games never allocate an engine.
    client = StockfishClient(load_settings())
    try:
        result = PGNAnalyzer(client).analyze(pgn)
    finally:
        client.close()
    payload = asdict(result)
    payload["initial_fen"] = initial_board.fen()
    for move in payload["moves"]:
        board = chess.Board(move["fen_before"])
        board.push_uci(move["best_move_uci"])
        move["best_fen"] = board.fen()
    return payload
