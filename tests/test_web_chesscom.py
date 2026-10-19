"""Offline regressions for public-game lookup, selection, and failure handling."""

import json
import os
from types import SimpleNamespace

import django
import pytest
import requests
from chessdotcom import ChessDotComClientError
from django.core.cache import cache
from django.test import Client, override_settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chess_analyzer.web.settings")
django.setup()

from chess_analyzer.web import chesscom  # noqa: E402

ENDPOINT = "/api/chesscom/games/"


def completed_game(end_time=1_792_300_000, **overrides):
    return {
        "rules": "chess",
        "pgn": '[White "Player"]\n[Black "Opponent"]\n\n1. e4 e5 *',
        "end_time": end_time,
        "white": {"username": "Player", "rating": 1400, "result": "win"},
        "black": {"username": "Opponent", "rating": 1450, "result": "resigned"},
        "time_class": "blitz",
        "time_control": "180+2",
        **overrides,
    }


@pytest.fixture(autouse=True)
def isolated_lookup_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def web_client():
    with override_settings(ALLOWED_HOSTS=["testserver"]):
        yield Client()


@pytest.fixture
def provider(monkeypatch):
    class FakeProvider:
        archives = {
            "archives": ["https://api.chess.com/pub/player/player/games/2026/10"]
        }
        monthly = {"games": [completed_game()]}
        calls = []

        def __init__(self, **kwargs):
            assert kwargs["user_agent"]
            assert kwargs["rate_limit_handler"].retries == 0

        def get_player_game_archives(self, username):
            self.calls.append(("archives", username))
            if isinstance(self.archives, Exception):
                raise self.archives
            return SimpleNamespace(json=self.archives)

        def get_player_games_by_month(self, username, *, year, month):
            self.calls.append(("month", username, year, month))
            if isinstance(self.monthly, Exception):
                raise self.monthly
            return SimpleNamespace(json=self.monthly)

    monkeypatch.setattr(chesscom, "ChessDotComClient", FakeProvider)
    return FakeProvider


def test_archive_lookup_and_normalization(web_client, provider):
    provider.archives = {
        "archives": [
            "https://api.chess.com/pub/player/player/games/2025/12",
            "https://untrusted.invalid/2026/2",
            "https://api.chess.com/pub/player/player/games/2026/10",
            "https://api.chess.com/pub/player/player/games/2026/10",
        ]
    }
    response = web_client.get(ENDPOINT, {"username": " Player_1 "})
    assert response.status_code == 200
    assert response.json() == {
        "username": "player_1",
        "archives": [
            {"year": 2026, "month": 10, "label": "2026-10"},
            {"year": 2026, "month": 2, "label": "2026-02"},
            {"year": 2025, "month": 12, "label": "2025-12"},
        ],
    }
    assert provider.calls == [("archives", "player_1")]
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("username", ["", " ", "x" * 26, "a/b", "a?b", "a b", "☃"])
def test_invalid_username_never_requests_provider(web_client, provider, username):
    assert web_client.get(ENDPOINT, {"username": username}).status_code == 400
    assert not provider.calls


def test_empty_archives_are_valid(web_client, provider):
    provider.archives = {"archives": []}
    response = web_client.get(ENDPOINT, {"username": "player"})
    assert response.status_code == 200
    assert response.json()["archives"] == []


def test_paginated_games_are_sorted_and_filtered(web_client, provider):
    provider.monthly = {
        "games": [completed_game(i) for i in range(1, 27)]
        + [completed_game(30, rules="atomic"), completed_game(31, pgn="")]
        + [completed_game(32, pgn="x" * 100_001)]
    }
    params = {"username": "player", "year": "2026", "month": "10"}
    first = web_client.get(ENDPOINT, params)
    assert first.status_code == 200
    data = first.json()
    assert data["total"] == 26
    assert data["pages"] == 2
    assert len(data["games"]) == 25
    assert data["games"][0]["end_time"] == 26
    assert data["games"][0]["white"]["rating"] == 1400
    assert data["games"][0]["pgn"].endswith("1. e4 e5 *")
    second = web_client.get(ENDPOINT, {**params, "page": "2"}).json()
    assert len(second["games"]) == 1
    assert second["games"][0]["end_time"] == 1
    assert provider.calls == [("month", "player", 2026, 10)]
    assert web_client.get(ENDPOINT, {**params, "page": 3}).status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        {"month": 10},
        {"year": 2026},
        {"year": 2026, "month": 0},
        {"year": 2026, "month": 13},
        {"year": 0, "month": 1},
        {"year": 10000, "month": 1},
        {"year": "abc", "month": 1},
        {"year": 2026, "month": 1, "page": 0},
        {"year": 2026, "month": 1, "page": "null"},
        {"year": 2026, "month": 1, "page": 100_001},
    ],
)
def test_invalid_month_or_page_never_fetches(web_client, provider, params):
    response = web_client.get(ENDPOINT, {"username": "player", **params})
    assert response.status_code == 400
    assert not provider.calls


def test_month_without_supported_games_is_empty(web_client, provider):
    provider.monthly = {"games": [completed_game(rules="atomic")]}
    response = web_client.get(
        ENDPOINT, {"username": "player", "year": 2026, "month": 10}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["games"] == []


def test_chess960_games_are_offered_with_variant_label(web_client, provider):
    pgn = '[Variant "Chess960"]\n[FEN "4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1"]\n\n1. O-O *'
    provider.monthly = {"games": [completed_game(rules="chess960", pgn=pgn)]}
    response = web_client.get(
        ENDPOINT, {"username": "player", "year": 2026, "month": 10}
    )
    assert response.status_code == 200
    game = response.json()["games"][0]
    assert game["rules"] == "chess960"
    assert game["pgn"] == pgn


def test_cache_normalizes_username_and_is_per_month(web_client, provider):
    for username in ("Player", "PLAYER", " player "):
        assert web_client.get(ENDPOINT, {"username": username}).status_code == 200
    assert provider.calls == [("archives", "player")]
    for month in (9, 9, 10):
        response = web_client.get(
            ENDPOINT, {"username": "player", "year": 2026, "month": month}
        )
        assert response.status_code == 200
    assert provider.calls[1:] == [
        ("month", "player", 2026, 9),
        ("month", "player", 2026, 10),
    ]


def provider_error(status):
    return ChessDotComClientError(status, "private details", {}, {}, "sensitive URL")


@pytest.mark.parametrize(
    "status, expected", [(404, 404), (410, 404), (429, 429), (500, 502)]
)
@pytest.mark.parametrize("stage", ["archives", "monthly"])
def test_upstream_status_is_safe(web_client, provider, status, expected, stage):
    setattr(provider, stage, provider_error(status))
    params = {"username": "player"}
    if stage == "monthly":
        params.update(year=2026, month=10)
    response = web_client.get(ENDPOINT, params)
    assert response.status_code == expected
    assert b"private" not in response.content
    assert b"sensitive" not in response.content
    if expected == 429:
        assert response["Retry-After"] == "60"
    assert chesscom._lookup_slot.acquire(blocking=False)
    chesscom._lookup_slot.release()


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_network_failures_are_safe_and_not_cached(web_client, provider, error):
    provider.archives = error("sensitive error")
    assert web_client.get(ENDPOINT, {"username": "player"}).status_code == 503
    provider.archives = {"archives": []}
    assert web_client.get(ENDPOINT, {"username": "player"}).status_code == 200
    assert len(provider.calls) == 2


@pytest.mark.parametrize("payload", [None, {}, {"archives": ["invalid"]}])
def test_malformed_archives_are_provider_errors(web_client, provider, payload):
    provider.archives = payload
    assert web_client.get(ENDPOINT, {"username": "player"}).status_code == 502


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"games": [None]},
        {"games": [completed_game(end_time=True)]},
        {"games": [completed_game(end_time=-1)]},
        {"games": [completed_game(end_time=253_402_300_800)]},
        {"games": [completed_game(white={})]},
    ],
)
def test_malformed_games_are_provider_errors(web_client, provider, payload):
    provider.monthly = payload
    response = web_client.get(
        ENDPOINT, {"username": "player", "year": 2026, "month": 10}
    )
    assert response.status_code == 502


def test_busy_lookup_does_not_make_a_request(web_client, provider):
    assert chesscom._lookup_slot.acquire(blocking=False)
    try:
        response = web_client.get(ENDPOINT, {"username": "player"})
        assert response.status_code == 429
        assert not provider.calls
    finally:
        chesscom._lookup_slot.release()


def test_only_get_is_allowed(web_client):
    assert web_client.post(ENDPOINT).status_code == 405


def test_actual_client_contract_uses_fixed_host_and_serial_requests(
    web_client, monkeypatch
):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert url.startswith("https://api.chess.com/pub/player/player/games/")
        assert kwargs["timeout"] == 30
        assert kwargs["verify"] is True
        assert kwargs["headers"]["User-Agent"]
        body = (
            {"archives": ["https://untrusted.invalid/2026/10"]}
            if url.endswith("archives")
            else {"games": [completed_game()]}
        )
        return SimpleNamespace(status_code=200, text=json.dumps(body))

    monkeypatch.setattr(requests, "get", get)
    assert web_client.get(ENDPOINT, {"username": "player"}).status_code == 200
    response = web_client.get(
        ENDPOINT, {"username": "player", "year": 2026, "month": 10}
    )
    assert response.status_code == 200
    assert len(response.json()["games"]) == 1
    assert len(calls) == 2
