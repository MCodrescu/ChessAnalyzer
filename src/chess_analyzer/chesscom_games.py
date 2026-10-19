"""Retrieve the latest completed game through an application-owned Chess.com client."""

import math
from typing import Any
from urllib.parse import urlsplit


def _archive_month(archive: object) -> tuple[int, int]:
    if not isinstance(archive, str):
        raise ValueError("Chess.com archives must contain URL strings.")
    try:
        path = urlsplit(archive).path.rstrip("/").split("/")
    except ValueError:
        raise ValueError("Chess.com archive URL has an invalid year/month.") from None
    if len(path) < 2 or any(
        not part.isascii() or not part.isdigit() for part in path[-2:]
    ):
        raise ValueError("Chess.com archive URL has an invalid year/month.")
    year, month = map(int, path[-2:])
    if year < 1 or not 1 <= month <= 12:
        raise ValueError("Chess.com archive URL has an invalid year/month.")
    return year, month


def get_archive_months(client: Any, username: str) -> list[tuple[int, int]]:
    """Return distinct archive (year, month) pairs, newest first.

    Use the caller-owned ChessDotComClient. Reject blank usernames and malformed
    responses with ValueError; propagate client/network errors unchanged. Parse
    dates locally and never request URLs supplied by an API response.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username must be a nonempty string.")
    payload = client.get_player_game_archives(username.strip()).json
    if not isinstance(payload, dict) or not isinstance(payload.get("archives"), list):
        raise ValueError("Chess.com archive response must contain an archives list.")
    return sorted({_archive_month(url) for url in payload["archives"]}, reverse=True)


def get_latest_game(
    client: Any, username: str, *, rules: str | None = None
) -> dict[str, Any]:
    """Return the user's most recently completed game, optionally filtering rules.

    Args:
        client: An initialized PyPI chess.com ChessDotComClient. Its timeout,
            User-Agent, and lifecycle remain the caller's responsibility.
        username: A nonblank username; surrounding whitespace is stripped.
        rules: Optional 'chess' or 'chess960' rules filter. With
            None, inspect the absolute latest game and reject unsupported rules.

    Returns:
        The original game dictionary, with nonblank PGN and positive numeric
        end_time. Monthly archives are visited newest first, stopping at the
        first month with matching games and selecting its greatest end_time.

    Raises:
        ValueError: Username or API payloads are malformed, no completed games
            exist, or the latest game is neither standard chess nor Chess960.
        Exception: Client/network/API exceptions propagate unchanged.

    Archive URL year/month tails are parsed locally; URLs are never requested
    directly. Empty months or months without matching rules trigger fallback.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username must be a nonempty string.")
    if rules is not None and rules not in ("chess", "chess960"):
        raise ValueError(
            "Only standard chess and Chess960 rules filters are supported."
        )
    username = username.strip()
    months = get_archive_months(client, username)
    if not months:
        raise ValueError("No completed games found: archive list is empty.")

    for year, month in months:
        payload = client.get_player_games_by_month(
            username, year=year, month=month
        ).json
        if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
            raise ValueError("Chess.com monthly response must contain a games list.")
        games = payload["games"]
        if not games:
            continue
        for game in games:
            if not isinstance(game, dict):
                raise ValueError("Chess.com games must be dictionaries.")
            end_time = game.get("end_time")
            if (
                isinstance(end_time, bool)
                or not isinstance(end_time, (int, float))
                or end_time <= 0
                or (isinstance(end_time, float) and not math.isfinite(end_time))
            ):
                raise ValueError(
                    "Chess.com game end_time must be numeric and positive."
                )
        candidates = (
            games
            if rules is None
            else [game for game in games if game.get("rules") == rules]
        )
        if not candidates:
            continue
        latest = max(candidates, key=lambda game: game["end_time"])
        if latest.get("rules") not in ("chess", "chess960"):
            raise ValueError("The latest game is not standard chess or Chess960.")
        pgn = latest.get("pgn")
        if not isinstance(pgn, str) or not pgn.strip():
            raise ValueError("The latest game has no nonempty PGN.")
        return latest

    raise ValueError("No completed games found matching the requested rules.")
