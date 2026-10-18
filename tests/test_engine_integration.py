"""Opt-in checks against an installed, live Stockfish binary (no network)."""

from dataclasses import replace

import chess
import pytest

from chess_analyzer import PGNAnalyzer, StockfishClient
from chess_analyzer.models import StockfishEngineError
from chess_analyzer.stockfish_client import resolve_stockfish_path

pytestmark = pytest.mark.integration


@pytest.fixture
def live_settings(settings):
    try:
        path = resolve_stockfish_path()
    except StockfishEngineError:
        pytest.skip("Install Stockfish before running integration tests.")
    return replace(
        settings,
        stockfish_path=path,
        analysis_depth=8,
        analysis_time_seconds=0.05,
        hash_mb=16,
    )


def test_real_engine_evaluates_game_and_exits(live_settings):
    with StockfishClient(live_settings) as client:
        engine = client._engine
        assert "Stockfish" in engine.id["name"]
        result = PGNAnalyzer(client).analyze("1. e4 e5 2. Nf3 Nc6 *")
        assert len(result.moves) == 4
        assert client.statistics.positions == 5
        for move in result.moves:
            board = chess.Board(move.fen_before)
            assert chess.Move.from_uci(move.best_move_uci) in board.legal_moves
            assert move.evaluation_before.cp is not None
    assert engine.returncode.result(timeout=5) == 0


def test_real_engine_finds_white_and_black_mates(live_settings):
    board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
    with StockfishClient(live_settings) as client:
        for position, sign in ((board, 1), (board.mirror(), -1)):
            evaluation = client.evaluate(position.fen())
            assert evaluation.mate == sign
            assert evaluation.cp is None
            position.push_uci(evaluation.best_move_uci)
            assert position.is_checkmate()
