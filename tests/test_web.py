"""Offline Django and adapter tests; no database or live engine required."""

import json
import os

import chess
import django
import pytest
from django.test import Client, override_settings

from chess_analyzer.config import ConfigurationError
from chess_analyzer.models import (
    InvalidPGNError,
    PositionEvaluation,
    StockfishEngineError,
)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chess_analyzer.web.settings")
django.setup()

from chess_analyzer.web import services, views  # noqa: E402


@pytest.fixture
def web_client():
    with override_settings(ALLOWED_HOSTS=["testserver"]):
        yield Client()


@pytest.fixture
def fake_engine(monkeypatch):
    class FakeClient:
        instances = []

        def __init__(self, settings):
            self.settings = settings
            self.closed = False
            self.fens = []
            self.instances.append(self)

        def evaluate(self, fen, *, chess960=False):
            self.fens.append(fen)
            board = chess.Board(fen, chess960=chess960)
            return PositionEvaluation(
                cp=25, best_move_uci=next(iter(board.legal_moves)).uci()
            )

        def close(self):
            self.closed = True

    monkeypatch.setattr(services, "StockfishClient", FakeClient)
    return FakeClient


def test_review_page(web_client):
    response = web_client.get("/")
    assert response.status_code == 200
    content = response.content.decode()
    assert "csrfmiddlewaretoken" in content
    assert 'id="board"' in content
    assert 'data-preview="best"' in content
    assert "/static/review/vendor/" in content
    assert "csrftoken" in response.cookies


def test_analysis_roundtrip(web_client, fake_engine):
    response = web_client.post(
        "/api/analyze/",
        {"pgn": '[White "Alice"]\n[Black "Bob"]\n\n1. e4 e5 *'},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["headers"]["White"] == "Alice"
    assert data["initial_fen"] == chess.STARTING_FEN
    assert data["chess960"] is False
    assert len(data["moves"]) == 2
    assert data["moves"][0]["played_move_san"] == "e4"
    assert data["moves"][1]["player"] == "black"
    for move in data["moves"]:
        board = chess.Board(move["fen_before"])
        board.push_uci(move["best_move_uci"])
        assert board.fen() == move["best_fen"]
    assert fake_engine.instances[0].closed
    assert len(fake_engine.instances[0].fens) == 3
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize(
    "body", ["{", "[]", "null", '{"pgn": 1}', '{"pgn": null}', "{}"]
)
def test_reject_invalid_json(web_client, body):
    response = web_client.post("/api/analyze/", body, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.parametrize("pgn", ["", "not a game", "1. e5 *", "1. e4 *\n\n1. d4 *"])
def test_invalid_pgn_never_allocates_engine(web_client, fake_engine, pgn):
    response = web_client.post(
        "/api/analyze/", {"pgn": pgn}, content_type="application/json"
    )
    assert response.status_code == 400
    assert not fake_engine.instances


def test_request_methods_and_content_type(web_client):
    assert web_client.get("/api/analyze/").status_code == 405
    assert web_client.post("/").status_code == 405
    assert web_client.post("/api/analyze/", {"pgn": "*"}).status_code == 415


def test_csrf_is_required():
    with override_settings(ALLOWED_HOSTS=["testserver"]):
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/analyze/", {"pgn": "*"}, content_type="application/json"
        )
        assert response.status_code == 403
        client.get("/")
        response = client.post(
            "/api/analyze/",
            {"pgn": "*"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        assert response.status_code == 200


def test_request_limits(web_client, fake_engine):
    with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=20):
        response = web_client.post(
            "/api/analyze/",
            json.dumps({"pgn": "x" * 30}),
            content_type="application/json",
        )
    assert response.status_code == 413
    with pytest.raises(InvalidPGNError, match="100,000"):
        services.analyze_pgn("x" * 100_001)
    assert not fake_engine.instances


def test_move_limit_before_engine_allocation(monkeypatch, fake_engine):
    monkeypatch.setattr(services, "MAX_PLIES", 1)
    with pytest.raises(InvalidPGNError, match="half-moves"):
        services.analyze_pgn("1. e4 e5 *")
    assert not fake_engine.instances


def test_empty_custom_start_never_searches(fake_engine):
    fen = "8/8/8/8/8/2k5/8/K7 b - - 0 42"
    result = services.analyze_pgn(f'[SetUp "1"]\n[FEN "{fen}"]\n\n*')
    assert result["initial_fen"] == fen
    assert not result["moves"]
    assert fake_engine.instances[0].closed
    assert not fake_engine.instances[0].fens


@pytest.mark.parametrize(
    "fen, moves",
    [
        ("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1", "1. O-O *"),
        ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "1. a8=Q+ *"),
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "1. exd6 *"),
        ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 42", "42... e5 *"),
    ],
)
def test_special_move_and_custom_fen_review(fake_engine, fen, moves):
    result = services.analyze_pgn(f'[SetUp "1"]\n[FEN "{fen}"]\n\n{moves}')
    move = result["moves"][0]
    board = chess.Board(fen)
    board.push_uci(move["played_move_uci"])
    assert move["fen_after"] == board.fen()
    assert move["fullmove_number"] == chess.Board(fen).fullmove_number
    assert chess.Board(move["best_fen"]).is_valid()


def test_mate_result_is_serializable(fake_engine):
    result = services.analyze_pgn("1. f3 e5 2. g4 Qh4# 0-1")
    assert result["moves"][-1]["evaluation_after"]["mate"] == 0
    assert result["moves"][-1]["evaluation_after"]["terminal_result"] == "0-1"
    assert result["moves"][-1]["estimated_cp_loss"] is None


def test_chess960_web_payload_and_castling_best_preview(
    web_client, fake_engine, monkeypatch
):
    def evaluate(self, fen, *, chess960=False):
        assert chess960
        self.fens.append(fen)
        board = chess.Board(fen, chess960=chess960)
        castles = list(board.generate_castling_moves())
        move = castles[0] if castles else next(iter(board.legal_moves))
        return PositionEvaluation(cp=25, best_move_uci=move.uci())

    monkeypatch.setattr(fake_engine, "evaluate", evaluate)
    fen = "4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1"
    pgn = f'[Variant "Chess960"]\n[SetUp "1"]\n[FEN "{fen}"]\n\n1. O-O *'
    response = web_client.post(
        "/api/analyze/", {"pgn": pgn}, content_type="application/json"
    )
    assert response.status_code == 200
    result = response.json()
    assert result["chess960"] is True
    assert result["initial_fen"] == fen
    move = result["moves"][0]
    assert move["played_move_uci"] == "c1f1"
    board = chess.Board(fen, chess960=True)
    board.push_uci(move["best_move_uci"])
    assert move["best_fen"] == board.fen()
    assert fake_engine.instances[0].closed


def test_client_closes_after_failure(monkeypatch, fake_engine):
    def fail(self, fen):
        raise StockfishEngineError("Internal path must not be exposed")

    monkeypatch.setattr(fake_engine, "evaluate", fail)
    with pytest.raises(StockfishEngineError):
        services.analyze_pgn("1. e4 *")
    assert fake_engine.instances[0].closed


@pytest.mark.parametrize("error", [StockfishEngineError, ConfigurationError])
def test_server_errors_are_safe_and_slot_is_released(web_client, monkeypatch, error):
    def fail(pgn):
        raise error("sensitive server details")

    monkeypatch.setattr(views, "analyze_pgn", fail)
    response = web_client.post(
        "/api/analyze/", {"pgn": "1. e4 *"}, content_type="application/json"
    )
    assert response.status_code == 503
    assert b"sensitive" not in response.content
    assert views._analysis_slot.acquire(blocking=False)
    views._analysis_slot.release()


def test_busy_request_is_rejected(web_client):
    assert views._analysis_slot.acquire(blocking=False)
    try:
        response = web_client.post(
            "/api/analyze/", {"pgn": "*"}, content_type="application/json"
        )
        assert response.status_code == 429
        assert response["Retry-After"] == "5"
    finally:
        views._analysis_slot.release()


def test_position_analysis_roundtrip(web_client, fake_engine):
    response = web_client.post(
        "/api/position/", {"fen": chess.STARTING_FEN}, content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["fen"] == chess.STARTING_FEN
    board = chess.Board(data["fen"])
    best = chess.Move.from_uci(data["best_move_uci"])
    assert best in board.legal_moves
    assert data["best_move_san"] == board.san(best)
    assert data["evaluation"]["cp"] == 25
    assert fake_engine.instances[0].closed
    assert fake_engine.instances[0].fens == [chess.STARTING_FEN]
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        {},
        {"fen": 12},
        {"fen": "invalid"},
        {"fen": "8/8/8/8/8/8/8/8 w - - 0 1"},
        {"fen": "x" * 201},
        {"fen": chess.STARTING_FEN, "chess960": "true"},
        {"fen": chess.STARTING_FEN, "chess960": 1},
    ],
)
def test_invalid_position_never_allocates_engine(web_client, fake_engine, data):
    response = web_client.post(
        "/api/position/", json.dumps(data), content_type="application/json"
    )
    assert response.status_code == 400
    assert "error" in response.json()
    assert not fake_engine.instances


def test_position_request_boundaries(web_client, fake_engine):
    assert web_client.get("/api/position/").status_code == 405
    assert web_client.post("/api/position/", {"fen": "*"}).status_code == 415
    assert (
        web_client.post(
            "/api/position/", "{", content_type="application/json"
        ).status_code
        == 400
    )
    with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=20):
        response = web_client.post(
            "/api/position/",
            {"fen": chess.STARTING_FEN},
            content_type="application/json",
        )
    assert response.status_code == 413
    with override_settings(ALLOWED_HOSTS=["testserver"]):
        client = Client(enforce_csrf_checks=True)
        assert (
            client.post(
                "/api/position/",
                {"fen": chess.STARTING_FEN},
                content_type="application/json",
            ).status_code
            == 403
        )
    assert not fake_engine.instances


@pytest.mark.parametrize(
    "fen, result",
    [
        ("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3", "0-1"),
        ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", "1/2-1/2"),
        ("7k/8/6K1/8/8/8/8/8 w - - 0 1", "1/2-1/2"),
    ],
)
def test_terminal_position_never_allocates_engine(web_client, fake_engine, fen, result):
    response = web_client.post(
        "/api/position/", {"fen": fen}, content_type="application/json"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["evaluation"]["terminal_result"] == result
    assert data["best_move_uci"] is None
    assert data["best_move_san"] is None
    assert not fake_engine.instances


def test_chess960_position_best_castling(web_client, fake_engine, monkeypatch):
    def evaluate(self, fen, *, chess960=False):
        assert chess960
        return PositionEvaluation(cp=25, best_move_uci="c1f1")

    monkeypatch.setattr(fake_engine, "evaluate", evaluate)
    response = web_client.post(
        "/api/position/",
        {"fen": "4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1", "chess960": True},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["best_move_san"] == "O-O"
    assert response.json()["best_move_uci"] == "c1f1"
    assert fake_engine.instances[0].closed


@pytest.mark.parametrize(
    "fen, uci, san",
    [
        ("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1", "e1g1", "O-O"),
        ("7k/P7/8/8/8/8/8/7K w - - 0 1", "a7a8n", "a8=N"),
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2", "e5d6", "exd6"),
    ],
)
def test_position_best_special_moves(
    web_client, fake_engine, monkeypatch, fen, uci, san
):
    def evaluate(self, fen, *, chess960=False):
        return PositionEvaluation(cp=25, best_move_uci=uci)

    monkeypatch.setattr(fake_engine, "evaluate", evaluate)
    response = web_client.post(
        "/api/position/", {"fen": fen}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["best_move_uci"] == uci
    assert response.json()["best_move_san"] == san
    assert fake_engine.instances[0].closed


@pytest.mark.parametrize("error", [StockfishEngineError, ConfigurationError])
def test_position_failure_is_safe_and_releases_slot(
    web_client, fake_engine, monkeypatch, error
):
    def fail(self, fen, *, chess960=False):
        raise error("sensitive server details")

    monkeypatch.setattr(fake_engine, "evaluate", fail)
    response = web_client.post(
        "/api/position/", {"fen": chess.STARTING_FEN}, content_type="application/json"
    )
    assert response.status_code == 503
    assert b"sensitive" not in response.content
    assert fake_engine.instances[0].closed
    assert views._analysis_slot.acquire(blocking=False)
    views._analysis_slot.release()


def test_position_shares_game_analysis_slot(web_client, fake_engine):
    assert views._analysis_slot.acquire(blocking=False)
    try:
        response = web_client.post(
            "/api/position/",
            {"fen": chess.STARTING_FEN},
            content_type="application/json",
        )
        assert response.status_code == 429
        assert response["Retry-After"] == "5"
        assert not fake_engine.instances
    finally:
        views._analysis_slot.release()


@pytest.mark.integration
def test_real_engine_web_payload(monkeypatch):
    monkeypatch.setenv("STOCKFISH_DEPTH", "2")
    monkeypatch.setenv("STOCKFISH_TIME_SECONDS", "0.02")
    result = services.analyze_pgn("1. e4 e5 2. Nf3 *")
    assert len(result["moves"]) == 3
    assert result["analysis_depth"] == 2
    for move in result["moves"]:
        board = chess.Board(move["fen_before"])
        assert chess.Move.from_uci(move["best_move_uci"]) in board.legal_moves


@pytest.mark.integration
def test_real_engine_variation_position(monkeypatch):
    monkeypatch.setenv("STOCKFISH_DEPTH", "2")
    monkeypatch.setenv("STOCKFISH_TIME_SECONDS", "0.02")
    board = chess.Board()
    board.push_san("d4")
    result = services.analyze_position(board.fen())
    best = chess.Move.from_uci(result["best_move_uci"])
    assert best in board.legal_moves
    assert result["best_move_san"] == board.san(best)
    assert result["evaluation"]["cp"] is not None
