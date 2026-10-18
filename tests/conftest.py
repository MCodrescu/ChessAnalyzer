"""Fail-closed HTTP/process boundaries and isolated environment settings."""

import os

import chess.engine
import pytest
import requests

from chess_analyzer.config import Settings


@pytest.fixture(autouse=True)
def isolate_environment_and_external_io(monkeypatch, request):
    """Unit tests never contact services, read real dotenv, or start an engine."""
    for name in set(os.environ) | {"PYTHON_DOTENV_DISABLED"}:
        if name.startswith("STOCKFISH_") or name == "PYTHON_DOTENV_DISABLED":
            monkeypatch.delenv(name, raising=False)
    # Record absent keys too, since dotenv mutates os.environ directly.
    for name in (
        "STOCKFISH_PATH",
        "STOCKFISH_DEPTH",
        "STOCKFISH_TIME_SECONDS",
        "STOCKFISH_TIMEOUT_SECONDS",
        "STOCKFISH_THREADS",
        "STOCKFISH_HASH_MB",
    ):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)

    def reject_request(*args, **kwargs):
        pytest.fail("Live HTTP requests are forbidden in tests.")

    def reject_engine(*args, **kwargs):
        pytest.fail("Live engine startup is forbidden in unit tests.")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_request)
    if request.node.get_closest_marker("integration"):
        if os.getenv("CHESS_ANALYZER_RUN_ENGINE_TESTS") != "1":
            pytest.skip("Set CHESS_ANALYZER_RUN_ENGINE_TESTS=1 for live engine tests.")
    else:
        monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", reject_engine)


@pytest.fixture
def settings():
    return Settings(analysis_depth=9, engine_timeout_seconds=4.25)
