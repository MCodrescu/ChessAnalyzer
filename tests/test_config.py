"""Settings validation and explicit, isolated environment loading."""

import os
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import pytest

from chess_analyzer import config
from chess_analyzer.config import ConfigurationError, Settings, load_settings


def test_settings_defaults_and_secret_safe_repr():
    settings = Settings(stockfish_api_key="dummy-config-key")
    assert settings.analysis_depth == config.DEFAULT_DEPTH
    assert settings.request_timeout_seconds == config.DEFAULT_TIMEOUT_SECONDS
    assert settings.stockfish_api_url == "https://stockfish.online/api/s/v2.php"
    assert "dummy-config-key" not in repr(settings)
    assert "analysis_depth=" in repr(settings)


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("stockfish_api_key", "replacement"),
        ("analysis_depth", 5),
        ("request_timeout_seconds", 1),
        ("stockfish_api_url", "https://example.invalid"),
    ],
)
def test_settings_are_frozen(settings, attribute, value):
    with pytest.raises(FrozenInstanceError):
        setattr(settings, attribute, value)


@pytest.mark.parametrize("key", [None, False, 123, "", " ", "\t\n"])
def test_settings_reject_invalid_keys(key):
    with pytest.raises(ConfigurationError, match="STOCKFISH_API_KEY"):
        Settings(stockfish_api_key=key)


@pytest.mark.parametrize("depth", [0, -1, 16, True, False, 1.0, "12", None])
def test_settings_reject_invalid_depth(depth):
    with pytest.raises(ConfigurationError, match="STOCKFISH_DEPTH"):
        Settings(stockfish_api_key="dummy", analysis_depth=depth)


@pytest.mark.parametrize("depth", [1, 15])
def test_settings_accept_depth_boundaries(depth):
    assert (
        Settings(stockfish_api_key="dummy", analysis_depth=depth).analysis_depth
        == depth
    )


@pytest.mark.parametrize(
    "timeout",
    [0, -1, -0.1, True, False, "30", None, float("nan"), float("inf"), -float("inf")],
)
def test_settings_reject_invalid_timeout(timeout):
    with pytest.raises(ConfigurationError, match="STOCKFISH_TIMEOUT_SECONDS"):
        Settings(stockfish_api_key="dummy", request_timeout_seconds=timeout)


@pytest.mark.parametrize("timeout", [1, 0.001, 7.5])
def test_settings_accept_positive_finite_timeout(timeout):
    settings = Settings(stockfish_api_key="dummy", request_timeout_seconds=timeout)
    assert settings.request_timeout_seconds == timeout


def test_load_environment_values(monkeypatch):
    monkeypatch.setenv(config.API_KEY_ENV, "dummy-environment-key")
    monkeypatch.setenv(config.DEPTH_ENV, " 15 ")
    monkeypatch.setenv(config.TIMEOUT_ENV, " 2.75 ")
    settings = load_settings()
    assert settings.stockfish_api_key == "dummy-environment-key"
    assert settings.analysis_depth == 15
    assert settings.request_timeout_seconds == 2.75


def test_explicit_dotenv_loads_and_populates_environment(tmp_path):
    path = tmp_path / "local.env"
    path.write_text(
        'STOCKFISH_API_KEY="dummy-file-key"\n'
        "STOCKFISH_DEPTH=7\nSTOCKFISH_TIMEOUT_SECONDS=1.5\n",
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.stockfish_api_key == "dummy-file-key"
    assert settings.analysis_depth == 7
    assert settings.request_timeout_seconds == 1.5
    assert os.environ[config.API_KEY_ENV] == "dummy-file-key"


def test_existing_environment_wins_over_dotenv(monkeypatch, tmp_path):
    path = tmp_path / "local.env"
    path.write_text(
        "STOCKFISH_API_KEY=dummy-file-key\n"
        "STOCKFISH_DEPTH=3\nSTOCKFISH_TIMEOUT_SECONDS=99\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(config.API_KEY_ENV, "dummy-process-key")
    monkeypatch.setenv(config.DEPTH_ENV, "11")
    monkeypatch.setenv(config.TIMEOUT_ENV, "2")
    settings = load_settings(str(path))
    assert settings.stockfish_api_key == "dummy-process-key"
    assert settings.analysis_depth == 11
    assert settings.request_timeout_seconds == 2


def test_blank_environment_key_does_not_fall_back_to_dotenv(monkeypatch, tmp_path):
    path = tmp_path / "local.env"
    path.write_text("STOCKFISH_API_KEY=dummy-file-key\n", encoding="utf-8")
    monkeypatch.setenv(config.API_KEY_ENV, " ")
    with pytest.raises(ConfigurationError, match="STOCKFISH_API_KEY"):
        load_settings(path)


def test_environment_only_does_not_discover_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "STOCKFISH_API_KEY=dummy-discovered-key\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    loader = Mock(side_effect=AssertionError("No dotenv loading without a path"))
    monkeypatch.setattr(config, "load_dotenv", loader)
    with pytest.raises(ConfigurationError, match="STOCKFISH_API_KEY"):
        load_settings()
    monkeypatch.setenv(config.API_KEY_ENV, "dummy-process-key")
    assert load_settings().stockfish_api_key == "dummy-process-key"
    loader.assert_not_called()


def test_missing_dotenv_is_allowed_with_environment_key(monkeypatch, tmp_path):
    monkeypatch.setenv(config.API_KEY_ENV, "dummy-key")
    assert load_settings(tmp_path / "missing.env").stockfish_api_key == "dummy-key"


@pytest.mark.parametrize("key", [None, "", "  \t"])
def test_loader_rejects_missing_or_blank_key(monkeypatch, key):
    if key is not None:
        monkeypatch.setenv(config.API_KEY_ENV, key)
    with pytest.raises(ConfigurationError, match="STOCKFISH_API_KEY"):
        load_settings()


@pytest.mark.parametrize("blank", ["", "  ", "\t"])
def test_blank_optional_environment_values_use_defaults(monkeypatch, blank):
    monkeypatch.setenv(config.API_KEY_ENV, "dummy-key")
    monkeypatch.setenv(config.DEPTH_ENV, blank)
    monkeypatch.setenv(config.TIMEOUT_ENV, blank)
    settings = load_settings()
    assert settings.analysis_depth == config.DEFAULT_DEPTH
    assert settings.request_timeout_seconds == config.DEFAULT_TIMEOUT_SECONDS


def test_blank_optional_dotenv_values_use_defaults(tmp_path):
    path = tmp_path / "blank.env"
    path.write_text(
        "STOCKFISH_API_KEY=dummy-key\nSTOCKFISH_DEPTH=\nSTOCKFISH_TIMEOUT_SECONDS=\n",
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.analysis_depth == config.DEFAULT_DEPTH
    assert settings.request_timeout_seconds == config.DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (config.DEPTH_ENV, value)
        for value in ("0", "16", "1.5", "True", "NaN", "dummy-invalid-depth")
    ]
    + [
        (config.TIMEOUT_ENV, value)
        for value in ("0", "-1", "nan", "inf", "-inf", "1e999", "True", "bad")
    ],
)
def test_loader_rejects_invalid_numeric_values_without_echoing(
    monkeypatch, name, value
):
    monkeypatch.setenv(config.API_KEY_ENV, "dummy-private-key")
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError, match=name) as error:
        load_settings()
    assert "dummy-private-key" not in str(error.value)
    assert "dummy-invalid-depth" not in str(error.value)


def test_invalid_utf8_dotenv_has_sanitized_error(tmp_path):
    path = tmp_path / "invalid.env"
    path.write_bytes(b"STOCKFISH_API_KEY=dummy-private-key\xff")
    with pytest.raises(ConfigurationError, match="Unable to read") as error:
        load_settings(path)
    assert "dummy-private-key" not in str(error.value)


def test_dotenv_read_failure_is_wrapped(monkeypatch, tmp_path):
    monkeypatch.setattr(
        config, "load_dotenv", Mock(side_effect=OSError("dummy-private-path"))
    )
    with pytest.raises(ConfigurationError, match="Unable to read") as error:
        load_settings(tmp_path / "unreadable.env")
    assert "dummy-private-path" not in str(error.value)


def test_malformed_dotenv_key_cannot_satisfy_required_setting(tmp_path):
    # python-dotenv warns and skips malformed bindings rather than raising.
    path = tmp_path / "malformed.env"
    path.write_text('STOCKFISH_API_KEY="unterminated\n', encoding="utf-8")
    with pytest.raises(ConfigurationError, match="STOCKFISH_API_KEY"):
        load_settings(path)
