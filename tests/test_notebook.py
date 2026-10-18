"""Execute the example notebook end to end with offline service doubles."""

import json
from html import escape
from pathlib import Path
from statistics import mean
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
        assert username == sample["black"]["username"]
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
            # Respect notebook-local username overrides without contacting a service.
            sample["black"]["username"] = namespace["CHESSCOM_USERNAME"]
    assert len(namespace["analysis"].moves) == 2
    assert len(namespace["my_moves"]) == 1
    assert namespace["player_colors"] == ["black"]
    assert len(calls) == 3


@pytest.mark.parametrize(
    ("matches", "expected"),
    [
        ([True, False, True], "2/3 (66.7%)"),
        ([True], "1/1 (100.0%)"),
        ([False], "0/1 (0.0%)"),
        ([], "N/A (no moves played)."),
    ],
)
def test_best_move_accuracy_counts_all_player_moves(matches, expected, capsys):
    root = Path(__file__).resolve().parents[1]
    notebook = json.loads(
        (root / "notebooks" / "analyze_latest_game.ipynb").read_text()
    )
    display_cell = notebook["cells"][-1]

    def move(player, is_best):
        return SimpleNamespace(
            fullmove_number=1,
            player=player,
            played_move_san="e4",
            best_move_san="e4",
            evaluation_before=PositionEvaluation(mate=3),
            evaluation_after=PositionEvaluation(mate=2),
            estimated_cp_loss=None,
            is_best_move=is_best,
        )

    namespace = {
        "analysis": SimpleNamespace(
            moves=[move("white", best) for best in matches] + [move("black", True)]
        ),
        "latest_game": {
            "white": {"username": "Tester"},
            "black": {"username": "Opponent"},
        },
        "CHESSCOM_USERNAME": "tester",
        "escape": escape,
        "mean": mean,
        "HTML": str,
        "display": lambda content: None,
    }
    source = "".join(display_cell["source"])
    exec(compile(source, "notebook-summary", "exec"), namespace)
    assert f"Best-move accuracy: {expected}" in capsys.readouterr().out
    assert namespace["total_moves"] == len(matches)
    assert namespace["best_move_count"] == sum(matches)
    assert namespace["accuracy"] == (
        pytest.approx(100 * sum(matches) / len(matches)) if matches else None
    )
