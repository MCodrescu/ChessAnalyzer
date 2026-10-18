"""Bounded, cached access to Chess.com's public completed-game archives."""

import re
from collections.abc import Callable
from threading import BoundedSemaphore
from typing import Any

from chessdotcom import (
    ChessDotComClient,
    ChessDotComClientError,
    ChessDotComError,
    RateLimitHandler,
)
from django.core.cache import cache
from requests import RequestException

from chess_analyzer.chesscom_games import get_archive_months
from chess_analyzer.config import CHESSCOM_USER_AGENT
from chess_analyzer.web.services import MAX_PGN_CHARACTERS

PAGE_SIZE = 25
CACHE_SECONDS = 60
_lookup_slot = BoundedSemaphore(1)


class ChessComLookupError(RuntimeError):
    """A safe provider failure message with its intended HTTP response status."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _username(username: str) -> str:
    if not isinstance(username, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,25}", username.strip()
    ):
        raise ValueError("Use a Chess.com username (1–25 letters, digits, _ or -).")
    return username.strip().lower()


def _fetch(key: str, fetch: Callable[[Any], Any]) -> Any:
    """Cache public archives briefly; serialize upstream requests per process."""
    cached = cache.get(key)
    if cached is not None:
        return cached
    if not _lookup_slot.acquire(blocking=False):
        raise ChessComLookupError(
            "A Chess.com lookup is running. Try again shortly.", 429
        )
    try:
        # The installed synchronous client uses a 30-second HTTP timeout.
        # Disable its default retry to return rate-limit errors promptly.
        client = ChessDotComClient(
            user_agent=CHESSCOM_USER_AGENT,
            rate_limit_handler=RateLimitHandler(retries=0),
        )
        result = fetch(client)
        cache.set(key, result, timeout=CACHE_SECONDS)
        return result
    except ChessDotComClientError as error:
        if error.status_code in (404, 410):
            raise ChessComLookupError(
                "Chess.com could not find that player or game archive.", 404
            ) from None
        if error.status_code == 429:
            raise ChessComLookupError(
                "Chess.com is rate limiting requests. Please try again later.", 429
            ) from None
        raise ChessComLookupError(
            "Chess.com is unavailable. Try again later."
        ) from None
    except RequestException:
        raise ChessComLookupError(
            "Unable to reach Chess.com. Please try again later.", 503
        ) from None
    except (ValueError, ChessDotComError):
        raise ChessComLookupError(
            "Chess.com returned an invalid archive response."
        ) from None
    finally:
        _lookup_slot.release()


def list_archives(username: str) -> dict:
    """Return a normalized username and its available months, newest first.

    Raises ValueError for invalid input and ChessComLookupError for upstream
    failures. Empty accounts return an empty archive list without an error.
    """
    username = _username(username)
    months = _fetch(
        f"chesscom:archives:{username}",
        lambda client: get_archive_months(client, username),
    )
    return {
        "username": username,
        "archives": [
            {"year": year, "month": month, "label": f"{year:04d}-{month:02d}"}
            for year, month in months
        ],
    }


def _standard_games(client: Any, username: str, year: int, month: int) -> list[dict]:
    payload = client.get_player_games_by_month(username, year=year, month=month).json
    if not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        raise ValueError("Missing games list.")
    games = []
    for game in payload["games"]:
        if not isinstance(game, dict):
            raise ValueError("Invalid game.")
        # Monthly archives only contain completed games. Exclude variants and
        # entries lacking a usable PGN rather than offering a broken import.
        if game.get("rules") != "chess":
            continue
        pgn = game.get("pgn")
        if not isinstance(pgn, str) or not pgn.strip():
            continue
        if len(pgn) > MAX_PGN_CHARACTERS:
            continue
        end_time = game.get("end_time")
        if type(end_time) is not int or not 0 < end_time < 253_402_300_800:
            raise ValueError("Invalid completion timestamp.")
        players = {}
        for color in ("white", "black"):
            player = game.get(color)
            if not isinstance(player, dict) or not isinstance(
                player.get("username"), str
            ):
                raise ValueError("Invalid player.")
            rating = player.get("rating")
            players[color] = {
                "username": player["username"],
                "rating": rating if type(rating) is int else None,
                "result": player.get("result", "unknown"),
            }
        games.append(
            {
                **players,
                "end_time": end_time,
                "time_class": str(game.get("time_class", "chess")),
                "time_control": str(game.get("time_control", "?")),
                "pgn": pgn,
            }
        )
    return sorted(games, key=lambda game: game["end_time"], reverse=True)


def list_games(username: str, *, year: int, month: int, page: int = 1) -> dict:
    """Return one page of completed standard games with PGNs for local import.

    Fetch only the requested month, not the whole account history. Validation
    precedes network access. Public results are cached in memory for 60 seconds;
    no game or analysis is stored in a database or written to disk.
    """
    username = _username(username)
    if type(year) is not int or not 1 <= year <= 9999:
        raise ValueError("Choose a valid archive year.")
    if type(month) is not int or not 1 <= month <= 12:
        raise ValueError("Choose a valid archive month.")
    if type(page) is not int or not 1 <= page <= 100_000:
        raise ValueError("Choose a valid game page.")
    games = _fetch(
        f"chesscom:games:{username}:{year}:{month}",
        lambda client: _standard_games(client, username, year, month),
    )
    pages = max(1, (len(games) + PAGE_SIZE - 1) // PAGE_SIZE)
    if page > pages:
        raise ValueError("That game page does not exist.")
    start = (page - 1) * PAGE_SIZE
    return {
        "username": username,
        "year": year,
        "month": month,
        "page": page,
        "pages": pages,
        "total": len(games),
        "games": games[start : start + PAGE_SIZE],
    }
