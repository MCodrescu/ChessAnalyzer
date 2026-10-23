"""Adapt engine results to a board-review payload without persisting PGNs."""

from dataclasses import asdict

import chess

from chess_analyzer.analyzer import PGNAnalyzer
from chess_analyzer.config import load_settings
from chess_analyzer.models import InvalidPGNError
from chess_analyzer.stockfish_client import StockfishClient, terminal_evaluation

MAX_PLIES = 600
MAX_PGN_CHARACTERS = 100_000


class InvalidPositionError(ValueError):
    """Input does not describe a valid supported chess position."""


def analyze_position(fen: str, *, chess960: bool = False) -> dict:
    """Search one valid FEN, returning its White-relative score and best move.

    Invalid positions raise InvalidPositionError before engine allocation. FEN does not
    carry repetition history. The owned engine is closed even on search failure.
    """
    if not isinstance(fen, str) or len(fen) > 200:
        raise InvalidPositionError("Provide a valid FEN of at most 200 characters.")
    if not isinstance(chess960, bool):
        raise InvalidPositionError("chess960 must be a boolean.")
    try:
        board = chess.Board(fen, chess960=chess960)
    except ValueError as error:
        raise InvalidPositionError("Provide a valid chess position FEN.") from error
    if not board.is_valid():
        raise InvalidPositionError("Provide a valid chess position FEN.")
    evaluation = terminal_evaluation(board)
    if evaluation is None:
        client = StockfishClient(load_settings())
        try:
            evaluation = client.evaluate(fen, chess960=chess960)
        finally:
            client.close()
    best = (
        chess.Move.from_uci(evaluation.best_move_uci)
        if evaluation.best_move_uci
        else None
    )
    return {
        "fen": fen,
        "evaluation": asdict(evaluation),
        "best_move_uci": evaluation.best_move_uci,
        "best_move_san": board.san(best) if best is not None else None,
    }


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
        board = chess.Board(move["fen_before"], chess960=initial_board.chess960)
        board.push_uci(move["best_move_uci"])
        move["best_fen"] = board.fen()
    return payload
