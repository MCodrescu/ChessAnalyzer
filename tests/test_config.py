"""Local search/resource validation and explicit environment loading."""

import os
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import pytest

from chess_analyzer import config
from chess_analyzer.config import ConfigurationError, Settings, load_settings


def test_defaults_need_no_key_or_engine():
    assert load_settings() == Settings()
    assert Settings().stockfish_path is None
    assert Settings().analysis_time_seconds == 0.2
    assert Settings().threads == 1
    assert Settings().hash_mb == 64


def test_settings_are_immutable(settings):
    with pytest.raises(FrozenInstanceError):
        settings.threads = 2


@pytest.mark.parametrize(
    ("attribute", "name", "maximum"),
    [
        ("analysis_depth", config.DEPTH_ENV, 128),
        ("threads", config.THREADS_ENV, 1024),
        ("hash_mb", config.HASH_ENV, 1048576),
    ],
)
@pytest.mark.parametrize("bad", [None, True, False, "2", 1.5, 0, -1, float("inf")])
def test_integer_limits_reject_invalid_values(attribute, name, maximum, bad):
    with pytest.raises(ConfigurationError, match=name):
        Settings(**{attribute: bad})
    with pytest.raises(ConfigurationError, match=name):
        Settings(**{attribute: maximum + 1})
    assert getattr(Settings(**{attribute: maximum}), attribute) == maximum
    assert getattr(Settings(**{attribute: 1}), attribute) == 1


@pytest.mark.parametrize(
    "attribute", ["engine_timeout_seconds", "analysis_time_seconds"]
)
@pytest.mark.parametrize(
    "bad", [True, False, "2", 0, -1, float("nan"), float("inf"), -float("inf")]
)
def test_search_times_must_be_positive_finite(attribute, bad):
    with pytest.raises(ConfigurationError):
        Settings(**{attribute: bad})


def test_only_analysis_time_can_be_none():
    assert Settings(analysis_time_seconds=None).analysis_time_seconds is None
    with pytest.raises(ConfigurationError, match=config.TIMEOUT_ENV):
        Settings(engine_timeout_seconds=None)


@pytest.mark.parametrize("bad", [True, 1, "", " ", "invalid\x00path"])
def test_executable_path_validation(bad):
    with pytest.raises(ConfigurationError, match=config.ENGINE_PATH_ENV):
        Settings(stockfish_path=bad)


def test_environment_values(monkeypatch):
    for name, value in {
        config.ENGINE_PATH_ENV: "/opt/engine with spaces/stockfish",
        config.DEPTH_ENV: " 24 ",
        config.ANALYSIS_TIME_ENV: " 0.5 ",
        config.TIMEOUT_ENV: " 20 ",
        config.THREADS_ENV: " 2 ",
        config.HASH_ENV: " 128 ",
    }.items():
        monkeypatch.setenv(name, value)
    assert load_settings() == Settings(
        stockfish_path="/opt/engine with spaces/stockfish",
        analysis_depth=24,
        analysis_time_seconds=0.5,
        engine_timeout_seconds=20,
        threads=2,
        hash_mb=128,
    )


@pytest.mark.parametrize("value", ["none", " None ", "NONE"])
def test_environment_depth_only(monkeypatch, value):
    monkeypatch.setenv(config.ANALYSIS_TIME_ENV, value)
    assert load_settings().analysis_time_seconds is None


@pytest.mark.parametrize(
    "name",
    [
        config.DEPTH_ENV,
        config.TIMEOUT_ENV,
        config.ANALYSIS_TIME_ENV,
        config.THREADS_ENV,
        config.HASH_ENV,
        config.ENGINE_PATH_ENV,
    ],
)
@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_blank_values_use_defaults(monkeypatch, name, blank):
    monkeypatch.setenv(name, blank)
    assert load_settings() == Settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (config.DEPTH_ENV, "129"),
        (config.DEPTH_ENV, "1.5"),
        (config.THREADS_ENV, "0"),
        (config.HASH_ENV, "bad"),
        (config.TIMEOUT_ENV, "none"),
        (config.TIMEOUT_ENV, "inf"),
        (config.ANALYSIS_TIME_ENV, "nan"),
        (config.ANALYSIS_TIME_ENV, "0"),
    ],
)
@pytest.mark.parametrize("source", ["environment", "dotenv"])
def test_loader_rejects_invalid_values(monkeypatch, tmp_path, name, value, source):
    path = None
    if source == "environment":
        monkeypatch.setenv(name, value)
    else:
        path = tmp_path / "invalid.env"
        path.write_text(f"{name}={value}\n")
    with pytest.raises(ConfigurationError, match=name):
        load_settings(path)


def test_dotenv_and_environment_precedence(monkeypatch, tmp_path):
    path = tmp_path / "local.env"
    path.write_text("STOCKFISH_DEPTH=24\nSTOCKFISH_THREADS=2\nSTOCKFISH_HASH_MB=128\n")
    monkeypatch.setenv(config.DEPTH_ENV, "15")
    monkeypatch.setenv(config.HASH_ENV, "")
    settings = load_settings(path)
    assert settings.analysis_depth == 15
    assert settings.threads == 2
    assert settings.hash_mb == 64
    assert os.environ[config.THREADS_ENV] == "2"


def test_no_implicit_dotenv_discovery(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("STOCKFISH_DEPTH=99\n")
    monkeypatch.chdir(tmp_path)
    loader = Mock(side_effect=AssertionError("Unexpected dotenv discovery"))
    monkeypatch.setattr(config, "load_dotenv", loader)
    assert load_settings() == Settings()
    loader.assert_not_called()


def test_missing_explicit_dotenv_is_allowed(tmp_path):
    assert load_settings(tmp_path / "missing.env") == Settings()


def test_invalid_utf8_is_wrapped(tmp_path):
    path = tmp_path / "bad.env"
    path.write_bytes(b"STOCKFISH_PATH=\xff")
    with pytest.raises(ConfigurationError, match="Unable to read"):
        load_settings(path)


def test_dotenv_read_failure_is_wrapped(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "load_dotenv", Mock(side_effect=OSError("private")))
    with pytest.raises(ConfigurationError, match="Unable to read") as error:
        load_settings(tmp_path / "bad.env")
    assert "private" not in str(error.value)


def test_obsolete_api_settings_are_not_required(monkeypatch):
    monkeypatch.setenv("STOCKFISH_API_KEY", "obsolete")
    monkeypatch.setenv("STOCKFISH_MAX_WORKERS", "invalid-old-setting")
    assert load_settings() == Settings()
