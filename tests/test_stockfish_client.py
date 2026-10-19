"""UCI boundary, native score conversion, discovery, and process ownership."""

from dataclasses import replace
from unittest.mock import Mock

import chess
import chess.engine
import pytest

from chess_analyzer import stockfish_client
from chess_analyzer.models import PositionEvaluation, StockfishEngineError
from chess_analyzer.stockfish_client import StockfishClient, resolve_stockfish_path


def engine_info(board=None, score=None):
    board = board if board is not None else chess.Board()
    return {
        "score": chess.engine.PovScore(
            score if score is not None else chess.engine.Cp(25), board.turn
        ),
        "pv": [next(iter(board.legal_moves))],
    }


@pytest.fixture
def engine_boundary(monkeypatch):
    engine = Mock(spec=chess.engine.SimpleEngine)
    engine.analyse.side_effect = lambda board, limit, **kwargs: engine_info(board)
    factory = Mock(return_value=engine)
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", factory)
    monkeypatch.setattr(
        stockfish_client,
        "resolve_stockfish_path",
        Mock(return_value="/engine/stockfish"),
    )
    return engine, factory


def test_one_process_reused_for_all_evaluations(settings, engine_boundary):
    engine, factory = engine_boundary
    settings = replace(settings, threads=2, hash_mb=128)
    with StockfishClient(settings) as client:
        assert client.evaluate(chess.STARTING_FEN).cp == 25
        assert len(client.evaluate_many([chess.STARTING_FEN] * 3)) == 3
        assert client.statistics.positions == 4
        assert client.statistics.search_seconds >= 0
        assert client._engine is engine
    factory.assert_called_once_with(
        ["/engine/stockfish"], timeout=settings.engine_timeout_seconds
    )
    engine.configure.assert_called_once_with({"Threads": 2, "Hash": 128})
    assert engine.analyse.call_count == 4
    engine.quit.assert_called_once_with()
    engine.close.assert_called_once_with()
    client.close()
    assert engine.quit.call_count == 1


@pytest.mark.parametrize("time_cap", [None, 0.01, 0.5])
def test_search_limits_and_native_centipawns(settings, engine_boundary, time_cap):
    engine, _ = engine_boundary
    engine.analyse.return_value = engine_info()
    engine.analyse.side_effect = None
    with StockfishClient(replace(settings, analysis_time_seconds=time_cap)) as client:
        assert client.evaluate(chess.STARTING_FEN).cp == 25  # Never multiply by 100.
    args, kwargs = engine.analyse.call_args
    assert args[0].fen() == chess.STARTING_FEN
    assert args[1].depth == settings.analysis_depth
    assert args[1].time == time_cap
    assert kwargs == {"info": chess.engine.INFO_SCORE | chess.engine.INFO_PV}


@pytest.mark.parametrize("turn", [chess.WHITE, chess.BLACK])
@pytest.mark.parametrize(
    "score",
    [
        chess.engine.Cp(37),
        chess.engine.Cp(-18),
        chess.engine.Mate(3),
        chess.engine.Mate(-2),
    ],
)
def test_all_scores_are_white_relative(settings, engine_boundary, turn, score):
    engine, _ = engine_boundary
    board = chess.Board()
    if turn == chess.BLACK:
        board.push_san("e4")
    engine.analyse.side_effect = None
    engine.analyse.return_value = engine_info(board, score)
    with StockfishClient(settings) as client:
        result = client.evaluate(board.fen())
    expected = score if turn == chess.WHITE else -score
    assert result.cp == expected.score()
    assert result.mate == expected.mate()
    assert chess.Move.from_uci(result.best_move_uci) in board.legal_moves


@pytest.mark.parametrize("fen", ["invalid", "8/8/8/8/8/8/8/8 w - - 0 1"])
def test_entire_batch_validated_before_engine_start(settings, engine_boundary, fen):
    _, factory = engine_boundary
    client = StockfishClient(settings)
    with pytest.raises(ValueError):
        client.evaluate_many([chess.STARTING_FEN, fen])
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("fen", "expected"),
    [
        (
            "7k/8/8/8/8/8/8/K7 w - - 0 1",
            PositionEvaluation(cp=0, terminal_result="1/2-1/2"),
        ),
        (
            "7k/5K2/6Q1/8/8/8/8/8 b - - 0 1",
            PositionEvaluation(cp=0, terminal_result="1/2-1/2"),
        ),
        (
            "7k/6Q1/5K2/8/8/8/8/8 b - - 0 1",
            PositionEvaluation(mate=0, terminal_result="1-0"),
        ),
        (
            "7k/8/8/8/8/8/R7/K7 w - - 150 76",
            PositionEvaluation(cp=0, terminal_result="1/2-1/2"),
        ),
    ],
)
def test_terminal_and_empty_batches_need_no_engine(
    settings, engine_boundary, fen, expected
):
    _, factory = engine_boundary
    client = StockfishClient(settings)
    assert client.evaluate_many([]) == []
    assert client.evaluate(fen) == expected
    assert client.evaluate_many([fen]) == [expected]
    assert client.statistics.positions == 0
    client.close()
    factory.assert_not_called()


def test_batch_order_and_black_sign(settings, engine_boundary):
    board = chess.Board()
    fens = [board.fen()]
    for san in ("e4", "e5", "Nf3"):
        board.push_san(san)
        fens.append(board.fen())
    with StockfishClient(settings) as client:
        assert [result.cp for result in client.evaluate_many(fens)] == [
            25,
            -25,
            25,
            -25,
        ]
    engine, _ = engine_boundary
    assert [call.args[0].fen() for call in engine.analyse.call_args_list] == fens


def test_chess960_single_batch_and_standard_switch(settings, engine_boundary):
    engine, _ = engine_boundary
    fen = "4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1"
    with StockfishClient(settings) as client:
        client.evaluate(fen, chess960=True)
        client.evaluate_many([fen, fen], chess960=True)
        client.evaluate(chess.STARTING_FEN)
    boards = [call.args[0] for call in engine.analyse.call_args_list]
    assert [board.chess960 for board in boards] == [True, True, True, False]
    assert all(board.is_valid() for board in boards)
    assert chess.Move.from_uci("c1f1") in boards[0].legal_moves


def test_chess960_castling_best_move_uses_rook_square(settings, engine_boundary):
    engine, _ = engine_boundary
    board = chess.Board("4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1", chess960=True)
    engine.analyse.side_effect = None
    engine.analyse.return_value = {
        "score": chess.engine.PovScore(chess.engine.Cp(25), board.turn),
        "pv": [board.parse_san("O-O-O")],
    }
    with StockfishClient(settings) as client:
        result = client.evaluate(board.fen(), chess960=True)
    assert result.best_move_uci == "c1a1"


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        OSError("failed"),
        chess.engine.EngineError("protocol"),
        chess.engine.EngineTerminatedError("crashed"),
    ],
)
def test_analysis_failure_stops_batch_and_closes(settings, engine_boundary, error):
    engine, _ = engine_boundary
    engine.analyse.side_effect = [engine_info(), error, engine_info()]
    with StockfishClient(settings) as client:
        with pytest.raises(StockfishEngineError, match="failed or timed out"):
            client.evaluate_many([chess.STARTING_FEN] * 3)
        assert client.statistics.positions == 2
        with pytest.raises(StockfishEngineError, match="closed"):
            client.evaluate(chess.STARTING_FEN)
    assert engine.analyse.call_count == 2
    engine.quit.assert_called_once()
    engine.close.assert_called_once()


@pytest.mark.parametrize(
    "error", [OSError(), TimeoutError(), chess.engine.EngineError()]
)
def test_startup_failures_are_wrapped(settings, engine_boundary, error):
    engine, factory = engine_boundary
    factory.side_effect = error
    client = StockfishClient(settings)
    with pytest.raises(StockfishEngineError, match="start/configure"):
        client.__enter__()
    assert client._engine is None
    engine.analyse.assert_not_called()


def test_configuration_failure_closes_started_engine(settings, engine_boundary):
    engine, _ = engine_boundary
    engine.configure.side_effect = chess.engine.EngineError("unsupported option")
    with pytest.raises(StockfishEngineError, match="thread/hash"):
        StockfishClient(settings).__enter__()
    engine.quit.assert_called_once()
    engine.close.assert_called_once()


def test_discovery_failure_closes_client_without_starting(
    settings, engine_boundary, monkeypatch
):
    _, factory = engine_boundary
    monkeypatch.setattr(
        stockfish_client,
        "resolve_stockfish_path",
        Mock(side_effect=StockfishEngineError("executable not found")),
    )
    client = StockfishClient(settings)
    with pytest.raises(StockfishEngineError, match="executable not found"):
        client.__enter__()
    with pytest.raises(StockfishEngineError, match="closed"):
        client.__enter__()
    factory.assert_not_called()


@pytest.mark.parametrize(
    "error", [TimeoutError(), chess.engine.EngineTerminatedError()]
)
def test_shutdown_forces_cleanup_without_masking_original_error(
    settings, engine_boundary, error
):
    engine, _ = engine_boundary
    engine.quit.side_effect = error
    with pytest.raises(ValueError, match="original"):
        with StockfishClient(settings):
            raise ValueError("original")
    engine.close.assert_called_once()


def test_interrupt_during_search_closes_engine(settings, engine_boundary):
    engine, _ = engine_boundary
    engine.analyse.side_effect = KeyboardInterrupt
    client = StockfishClient(settings)
    with pytest.raises(KeyboardInterrupt):
        client.evaluate(chess.STARTING_FEN)
    engine.close.assert_called_once()


@pytest.mark.parametrize(
    "info",
    [
        {},
        {"pv": [chess.Move.from_uci("e2e4")]},
        {"score": chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)},
        {
            "score": chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE),
            "pv": [chess.Move.from_uci("e2e5")],
        },
        {
            "score": chess.engine.PovScore(chess.engine.Mate(0), chess.WHITE),
            "pv": [chess.Move.from_uci("e2e4")],
        },
    ],
)
def test_invalid_engine_results_raise_and_close(settings, engine_boundary, info):
    engine, _ = engine_boundary
    engine.analyse.side_effect = None
    engine.analyse.return_value = info
    client = StockfishClient(settings)
    with pytest.raises(StockfishEngineError):
        client.evaluate(chess.STARTING_FEN)
    engine.close.assert_called_once()


def test_closed_client_rejects_even_empty_or_terminal_work(settings, engine_boundary):
    client = StockfishClient(settings)
    client.close()
    for action in (
        client.__enter__,
        lambda: client.evaluate_many([]),
        lambda: client.evaluate(chess.STARTING_FEN),
    ):
        with pytest.raises(StockfishEngineError, match="closed"):
            action()


def test_discover_path_and_linux_fallback(monkeypatch, tmp_path):
    binary = tmp_path / "stockfish"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    lookup = Mock(side_effect=[None, str(binary)])
    monkeypatch.setattr(stockfish_client, "which", lookup)
    assert resolve_stockfish_path() == str(binary)
    assert [call.args[0] for call in lookup.call_args_list] == [
        "stockfish",
        "/usr/games/stockfish",
    ]


def test_explicit_path_with_spaces_is_preserved(tmp_path):
    binary = tmp_path / "stockfish with spaces"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    assert resolve_stockfish_path(str(binary)) == str(binary)


def test_explicit_missing_path_never_falls_back(monkeypatch):
    lookup = Mock(return_value=None)
    monkeypatch.setattr(stockfish_client, "which", lookup)
    with pytest.raises(StockfishEngineError, match="apt-get install"):
        resolve_stockfish_path("/missing/stockfish")
    lookup.assert_called_once_with("/missing/stockfish")


def test_nonexecutable_file_rejected(tmp_path):
    binary = tmp_path / "not-executable"
    binary.write_text("not a binary")
    binary.chmod(0o644)
    with pytest.raises(StockfishEngineError, match="not executable"):
        resolve_stockfish_path(str(binary))
