"""Isolated settings and a fail-closed network boundary for the entire suite."""

import pytest
import requests

from chess_analyzer.config import API_KEY_ENV, DEPTH_ENV, TIMEOUT_ENV, Settings


@pytest.fixture(autouse=True)
def isolate_environment_and_network(monkeypatch):
    """Never read developer credentials or allow an accidental live request."""
    for name in (API_KEY_ENV, DEPTH_ENV, TIMEOUT_ENV, "PYTHON_DOTENV_DISABLED"):
        # Record even absent keys so dotenv's direct mutations are undone too.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)

    def reject_request(*args, **kwargs):
        pytest.fail("Live HTTP requests are forbidden in unit tests.")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_request)


@pytest.fixture
def settings():
    return Settings(
        stockfish_api_key="dummy-test-key-not-a-secret",
        analysis_depth=9,
        request_timeout_seconds=4.25,
    )
