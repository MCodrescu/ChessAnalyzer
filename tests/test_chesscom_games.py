"""Offline contract tests for latest completed Chess.com game retrieval."""

from types import SimpleNamespace

import pytest

from chess_analyzer.chesscom_games import get_latest_game


def archive(year, month):
    return f"https://api.chess.com/pub/player/player/games/{year}/{month}"


def game(end_time, **overrides):
    return {"end_time": end_time, "rules": "chess", "pgn": "1. e4 *", **overrides}


class FakeClient:
    def __init__(self, archives, monthly=None):
        self.archives = archives
        self.monthly = monthly or {}
        self.calls = []

    def get_player_game_archives(self, username):
        self.calls.append(("archives", username))
        if isinstance(self.archives, Exception):
            raise self.archives
        return SimpleNamespace(json=self.archives)

    def get_player_games_by_month(self, username, *, year, month):
        self.calls.append(("month", username, year, month))
        payload = self.monthly[year, month]
        if isinstance(payload, Exception):
            raise payload
        return SimpleNamespace(json=payload)


def test_unordered_archives_and_games_stop_after_newest_month():
    latest = game(30.5)
    client = FakeClient(
        {"archives": [archive(2025, 12), archive(2026, 2), archive(2026, 10)]},
        {(2026, 10): {"games": [game(20), latest, game(10)]}},
    )
    assert get_latest_game(client, " player ") is latest
    assert client.calls == [("archives", "player"), ("month", "player", 2026, 10)]


def test_rules_filter_selects_latest_standard_game():
    latest_standard = game(20)
    client = FakeClient(
        {"archives": [archive(2026, 10)]},
        {
            (2026, 10): {
                "games": [game(30, rules="chess960"), game(10), latest_standard]
            }
        },
    )
    assert get_latest_game(client, "player", rules="chess") is latest_standard


def test_rules_filter_falls_back_to_older_month():
    latest_standard = game(10)
    client = FakeClient(
        {"archives": [archive(2026, 10), archive(2026, 9)]},
        {
            (2026, 10): {"games": [game(30, rules="chess960")]},
            (2026, 9): {"games": [latest_standard]},
        },
    )
    assert get_latest_game(client, "player", rules="chess") is latest_standard


def test_rules_filter_without_matching_games():
    client = FakeClient(
        {"archives": [archive(2026, 10)]},
        {(2026, 10): {"games": [game(30, rules="chess960")]}},
    )
    with pytest.raises(ValueError, match="No completed games"):
        get_latest_game(client, "player", rules="chess")


def test_empty_newest_months_fall_back_in_numeric_order():
    latest = game(50)
    client = FakeClient(
        {
            "archives": [
                archive(2025, 12),
                archive(2026, 2),
                archive(2026, 10),
                archive(2024, 1),
            ]
        },
        {
            (2026, 10): {"games": []},
            (2026, 2): {"games": []},
            (2025, 12): {"games": [latest]},
        },
    )
    assert get_latest_game(client, "player") is latest
    assert client.calls[1:] == [
        ("month", "player", 2026, 10),
        ("month", "player", 2026, 2),
        ("month", "player", 2025, 12),
    ]


@pytest.mark.parametrize("archives", [[], [archive(2026, 10), archive(2026, 2)]])
def test_no_completed_games(archives):
    client = FakeClient(
        {"archives": archives},
        {(2026, 10): {"games": []}, (2026, 2): {"games": []}},
    )
    with pytest.raises(ValueError, match="No completed games"):
        get_latest_game(client, "player")


@pytest.mark.parametrize("username", [None, 12, True, "", " \t\n"])
def test_username_validation_precedes_requests(username):
    client = FakeClient({"archives": []})
    with pytest.raises(ValueError, match="username"):
        get_latest_game(client, username)
    assert client.calls == []


@pytest.mark.parametrize(
    "payload", [None, [], "body", {}, {"archives": None}, {"archives": "url"}]
)
def test_malformed_archive_payload(payload):
    client = FakeClient(payload)
    with pytest.raises(ValueError, match="archives list"):
        get_latest_game(client, "player")
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        None,
        12,
        "",
        "https://example.com/no-month",
        archive("year", 2),
        archive(2026, 0),
        archive(2026, 13),
        archive(0, 1),
        archive(2026, "2.5"),
        "https://[invalid/2026/10",
    ],
)
def test_malformed_archive_entries_fail_before_month_requests(url):
    client = FakeClient({"archives": [archive(2026, 10), url]})
    with pytest.raises(ValueError, match="archive"):
        get_latest_game(client, "player")
    assert len(client.calls) == 1


def test_archive_url_only_supplies_numeric_month_not_request_target():
    latest = game(10)
    client = FakeClient(
        {"archives": ["https://untrusted.invalid/2026/2/?ignored=1#fragment"]},
        {(2026, 2): {"games": [latest]}},
    )
    assert get_latest_game(client, "player") is latest
    assert client.calls[-1] == ("month", "player", 2026, 2)


@pytest.mark.parametrize(
    "payload", [None, [], "body", {}, {"games": None}, {"games": {}}]
)
def test_malformed_monthly_payload_does_not_fall_back(payload):
    client = FakeClient(
        {"archives": [archive(2026, 10), archive(2026, 2)]}, {(2026, 10): payload}
    )
    with pytest.raises(ValueError, match="games list"):
        get_latest_game(client, "player")
    assert len(client.calls) == 2


@pytest.mark.parametrize("entry", [None, [], "game", 1])
def test_game_entries_must_be_dictionaries(entry):
    client = FakeClient(
        {"archives": [archive(2026, 10)]},
        {(2026, 10): {"games": [game(10), entry]}},
    )
    with pytest.raises(ValueError, match="dictionaries"):
        get_latest_game(client, "player")


@pytest.mark.parametrize(
    "end_time",
    [None, True, False, "20", 0, -1, [], {}, float("nan"), float("inf")],
)
def test_invalid_end_time_is_not_silently_skipped(end_time):
    client = FakeClient(
        {"archives": [archive(2026, 10)]},
        {(2026, 10): {"games": [game(10), game(end_time)]}},
    )
    with pytest.raises(ValueError, match="end_time"):
        get_latest_game(client, "player")


def test_missing_end_time():
    client = FakeClient(
        {"archives": [archive(2026, 10)]},
        {(2026, 10): {"games": [{"rules": "chess", "pgn": "1. e4 *"}]}},
    )
    with pytest.raises(ValueError, match="end_time"):
        get_latest_game(client, "player")


@pytest.mark.parametrize("rules", ["bughouse", None, "", 12])
def test_latest_unsupported_variant_is_not_skipped(rules):
    client = FakeClient(
        {"archives": [archive(2026, 10), archive(2026, 2)]},
        {(2026, 10): {"games": [game(20, rules=rules), game(10)]}},
    )
    with pytest.raises(ValueError, match="latest game is not standard chess"):
        get_latest_game(client, "player")
    assert len(client.calls) == 2


@pytest.mark.parametrize("field", ["rules", "pgn"])
def test_missing_latest_game_fields(field):
    latest = game(20)
    del latest[field]
    client = FakeClient(
        {"archives": [archive(2026, 10)]}, {(2026, 10): {"games": [latest]}}
    )
    with pytest.raises(
        ValueError, match="standard chess" if field == "rules" else "PGN"
    ):
        get_latest_game(client, "player")


@pytest.mark.parametrize("pgn", [None, "", " \n\t", 12, {}])
def test_latest_missing_or_blank_pgn_does_not_fall_back(pgn):
    client = FakeClient(
        {"archives": [archive(2026, 10), archive(2026, 2)]},
        {(2026, 10): {"games": [game(20, pgn=pgn), game(10)]}},
    )
    with pytest.raises(ValueError, match="PGN"):
        get_latest_game(client, "player")
    assert len(client.calls) == 2


def test_older_unsupported_or_missing_pgn_game_does_not_hide_latest():
    latest = game(20)
    client = FakeClient(
        {"archives": [archive(2026, 10)]},
        {(2026, 10): {"games": [game(10, rules="chess960", pgn=None), latest]}},
    )
    assert get_latest_game(client, "player") is latest


@pytest.mark.parametrize("rules", [None, "chess960"])
def test_latest_chess960_game_is_supported(rules):
    latest = game(20, rules="chess960")
    client = FakeClient(
        {"archives": [archive(2026, 10)]},
        {(2026, 10): {"games": [latest, game(30)]}},
    )
    if rules is None:
        latest["end_time"] = 40
    assert get_latest_game(client, "player", rules=rules) is latest


@pytest.mark.parametrize("stage", ["archives", "month"])
@pytest.mark.parametrize("error_type", [RuntimeError, TimeoutError, ValueError])
def test_api_exceptions_propagate_unchanged_without_fallback(stage, error_type):
    error = error_type("provider failure")
    client = FakeClient(
        error
        if stage == "archives"
        else {"archives": [archive(2026, 10), archive(2026, 2)]},
        {(2026, 10): error},
    )
    with pytest.raises(error_type) as caught:
        get_latest_game(client, "player")
    assert caught.value is error
    assert len(client.calls) == (1 if stage == "archives" else 2)
