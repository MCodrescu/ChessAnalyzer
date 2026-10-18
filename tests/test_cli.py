"""CLI file/engine checks using a deterministic evaluator, never subprocesses."""

import json
from unittest.mock import Mock

import pytest

from chess_analyzer import __main__ as cli
from chess_analyzer.config import Settings
from chess_analyzer.models import PositionEvaluation, StockfishEngineError


@pytest.fixture
def client(monkeypatch):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.evaluate.return_value = PositionEvaluation(cp=23, best_move_uci="e2e4")
    monkeypatch.setattr(cli, "StockfishClient", Mock(return_value=client))
    return client


def test_check_engine_json(client, capsys):
    assert cli.main(["--check-engine"]) == 0
    assert json.loads(capsys.readouterr().out)["cp"] == 23
    client.evaluate.assert_called_once()
    client.__exit__.assert_called_once()


def test_pgn_file_json(client, monkeypatch, tmp_path, capsys):
    client.settings = Settings()
    path = tmp_path / "game.pgn"
    path.write_text('[Event "Empty game"]\n\n*')
    assert cli.main([str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["moves"] == []
    assert output["analysis_time_seconds"] == 0.2


def test_explicit_env_file_only(client, monkeypatch, tmp_path):
    path = tmp_path / "custom.env"
    loader = Mock(return_value=Settings())
    monkeypatch.setattr(cli, "load_settings", loader)
    assert cli.main(["--env-file", str(path), "--check-engine"]) == 0
    loader.assert_called_once_with(path)


def test_engine_error_returns_failure(client, capsys):
    client.evaluate.side_effect = StockfishEngineError("engine unavailable")
    assert cli.main(["--check-engine"]) == 1
    assert "engine unavailable" in capsys.readouterr().err


def test_missing_pgn_returns_failure_without_startup(client, tmp_path, capsys):
    assert cli.main([str(tmp_path / "missing.pgn")]) == 1
    assert "Analysis failed" in capsys.readouterr().err
    client.__enter__.assert_not_called()


@pytest.mark.parametrize("argv", [[], ["game.pgn", "--check-engine"]])
def test_requires_exactly_one_operation(argv):
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2
