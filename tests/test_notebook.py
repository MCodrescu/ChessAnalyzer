"""Execute the example notebook end to end with offline service doubles."""

import json
from pathlib import Path
from types import SimpleNamespace

import chess
import pytest

from chess_analyzer import config
from chess_analyzer.models import PositionEvaluation
from chess_analyzer.stockfish_client import StockfishClient


def test_latest_game_notebook_offline(monkeypatch):
    chessdotcom = pytest.importorskip("chessdotcom")
    pytest.importorskip("IPython")
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root / "notebooks")
    sample = {
        "end_time": 1_700_000_000,
        "rules": "chess",
        "pgn": "1. e4 e5 *",
        "white": {"username": "Opponent"},
        "black": {"username": config.CHESSCOM_USERNAME},
    }
    calls = []

    def archives(username):
        assert username == config.CHESSCOM_USERNAME
        return SimpleNamespace(
            json={"archives": ["https://api.chess.com/pub/player/mcodr/games/2023/11"]}
        )

    def monthly(username, *, year, month):
        assert (year, month) == (2023, 11)
        return SimpleNamespace(json={"games": [sample]})

    def evaluate(self, fen):
        board = chess.Board(fen)
        calls.append(fen)
        return PositionEvaluation(
            cp=10, best_move_uci=next(iter(board.legal_moves)).uci()
        )

    fake_client = SimpleNamespace(
        get_player_game_archives=archives, get_player_games_by_month=monthly
    )
    monkeypatch.setattr(chessdotcom, "ChessDotComClient", lambda **kwargs: fake_client)
    monkeypatch.setattr(StockfishClient, "_start", lambda self: None)
    monkeypatch.setattr(
        StockfishClient,
        "evaluate_many",
        lambda self, fens: [evaluate(self, fen) for fen in fens],
    )
    # Never read the user's real dotenv file during tests.
    monkeypatch.setattr(
        config,
        "load_settings",
        lambda path: config.Settings(),
    )
    notebook = json.loads(
        (root / "notebooks" / "analyze_latest_game.ipynb").read_text()
    )
    namespace = {}
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            exec(compile(source, f"notebook-cell-{index + 1}", "exec"), namespace)
    assert len(namespace["analysis"].moves) == 2
    assert len(namespace["my_moves"]) == 1
    assert namespace["player_colors"] == ["black"]
    assert len(calls) == 3
