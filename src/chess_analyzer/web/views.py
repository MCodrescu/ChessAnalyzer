"""CSRF-protected local analysis HTTP endpoints."""

import json
import logging
import sqlite3
from collections.abc import Callable
from threading import BoundedSemaphore

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from chess_analyzer.config import ConfigurationError
from chess_analyzer.models import InvalidPGNError, StockfishEngineError
from chess_analyzer.web.chesscom import ChessComLookupError, list_archives, list_games
from chess_analyzer.web.rating import validate_rating_pgn
from chess_analyzer.web.rating_jobs import RatingJobStore, RatingQueueFull
from chess_analyzer.web.services import (
    InvalidPositionError,
    analyze_pgn,
    analyze_position,
    validate_game_input,
)

# One CPU-intensive job per web process. Multi-worker deployments need a queue
# with a global concurrency limit, not additional unconstrained web workers.
_analysis_slot = BoundedSemaphore(1)
logger = logging.getLogger(__name__)
RATING_STORAGE_ERROR = (
    "Performance rating storage is unavailable. "
    "Check RATING_JOB_DATABASE and its directory permissions."
)


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    """Render the PGN import form and Chessground review workspace."""
    return render(request, "review/index.html")


@never_cache
@require_GET
def chesscom_games(request: HttpRequest) -> JsonResponse:
    """List a public player's archives, or a page of games in one chosen month."""
    username = request.GET.get("username", "")
    try:
        if any(key in request.GET for key in ("year", "month", "page")):
            result = list_games(
                username,
                year=int(request.GET.get("year", "")),
                month=int(request.GET.get("month", "")),
                page=int(request.GET.get("page", "1")),
            )
        else:
            result = list_archives(username)
        return JsonResponse(result)
    except ValueError:
        return JsonResponse(
            {"error": "Provide a valid Chess.com username, archive month, and page."},
            status=400,
        )
    except ChessComLookupError as error:
        response = JsonResponse({"error": str(error)}, status=error.status)
        if error.status == 429:
            response["Retry-After"] = "60"
        return response


@never_cache
@require_POST
def analyze(request: HttpRequest) -> JsonResponse:
    """Analyze one JSON PGN; return validation, engine, and busy errors safely."""
    if request.content_type != "application/json":
        return JsonResponse({"error": "Send a JSON object containing pgn."}, status=415)
    try:
        data = json.loads(request.body)
    except RequestDataTooBig:
        return JsonResponse({"error": "The PGN request is too large."}, status=413)
    except (ValueError, UnicodeError):
        return JsonResponse({"error": "Invalid JSON request."}, status=400)
    if not isinstance(data, dict) or not isinstance(data.get("pgn"), str):
        return JsonResponse({"error": "Provide a PGN string."}, status=400)
    if settings.RATING_MODEL_DIRECTORY:
        return _queue_game_review(data["pgn"])
    return _analysis_response(lambda: analyze_pgn(data["pgn"]))


def _queue_game_review(pgn: str) -> JsonResponse:
    """Queue one shared review/rating pass without holding an HTTP request open.

    Args:
        pgn: Original game, validated before storing or allocating an engine.

    Returns:
        HTTP 202 job state, or safe validation, busy, and storage errors.
    """
    try:
        validate_game_input(pgn)
        job = RatingJobStore().submit(pgn)
    except InvalidPGNError as error:
        return JsonResponse({"error": str(error)}, status=400)
    except RatingQueueFull as error:
        response = JsonResponse({"error": str(error)}, status=429)
        response["Retry-After"] = "10"
        return response
    except (OSError, sqlite3.Error):
        logger.exception("Shared game analysis storage failed during submission")
        return JsonResponse({"error": RATING_STORAGE_ERROR}, status=503)
    return JsonResponse(job.model_dump(mode="json"), status=202)


@never_cache
@require_POST
def position_analysis(request: HttpRequest) -> JsonResponse:
    """Search a variation position using the same bounded local engine slot."""
    if request.content_type != "application/json":
        return JsonResponse({"error": "Send a JSON object containing fen."}, status=415)
    try:
        data = json.loads(request.body)
    except RequestDataTooBig:
        return JsonResponse({"error": "The position request is too large."}, status=413)
    except (ValueError, UnicodeError):
        return JsonResponse({"error": "Invalid JSON request."}, status=400)
    if not isinstance(data, dict) or not isinstance(data.get("fen"), str):
        return JsonResponse({"error": "Provide a FEN string."}, status=400)
    return _analysis_response(
        lambda: analyze_position(data["fen"], chess960=data.get("chess960", False))
    )


@never_cache
@require_POST
def rating_submit(request: HttpRequest) -> JsonResponse:
    """Validate and enqueue a game without running inference in the request.

    Args:
        request: CSRF-protected JSON request containing the original PGN.

    Returns:
        A job ID with HTTP 202, or a safe validation/availability error.
    """
    if not settings.RATING_MODEL_DIRECTORY:
        return JsonResponse(
            {"error": "Performance ratings are not configured."}, status=503
        )
    if request.content_type != "application/json":
        return JsonResponse({"error": "Send a JSON object containing pgn."}, status=415)
    try:
        data = json.loads(request.body)
    except RequestDataTooBig:
        return JsonResponse({"error": "The PGN request is too large."}, status=413)
    except (ValueError, UnicodeError):
        return JsonResponse({"error": "Invalid JSON request."}, status=400)
    if not isinstance(data, dict) or not isinstance(data.get("pgn"), str):
        return JsonResponse({"error": "Provide a PGN string."}, status=400)
    try:
        validate_rating_pgn(data["pgn"])
        job = RatingJobStore().submit(data["pgn"])
    except InvalidPGNError as error:
        return JsonResponse({"error": str(error)}, status=400)
    except RatingQueueFull as error:
        response = JsonResponse({"error": str(error)}, status=429)
        response["Retry-After"] = "10"
        return response
    except (OSError, sqlite3.Error):
        logger.exception("Rating job storage failed during submission")
        return JsonResponse({"error": RATING_STORAGE_ERROR}, status=503)
    return JsonResponse(job.model_dump(mode="json"), status=202)


@never_cache
@require_GET
def rating_status(request: HttpRequest, job_id: str) -> JsonResponse:
    """Return job state to the holder of its unguessable capability ID.

    Args:
        request: Same-origin status request.
        job_id: Identifier returned by rating_submit.

    Returns:
        Public job state without PGN, or HTTP 404 after expiry.
    """
    if not settings.RATING_MODEL_DIRECTORY:
        return JsonResponse(
            {"error": "Performance ratings are not configured."}, status=503
        )
    try:
        job = RatingJobStore().get(job_id)
    except (OSError, sqlite3.Error):
        logger.exception("Rating job storage failed during status lookup")
        return JsonResponse({"error": RATING_STORAGE_ERROR}, status=503)
    if job is None:
        return JsonResponse(
            {"error": "Rating job expired or was not found."}, status=404
        )
    return JsonResponse(job.model_dump(mode="json"))


def _analysis_response(analyze_input: Callable[[], dict]) -> JsonResponse:
    """Share resource limits and safe error responses across engine endpoints."""
    if not _analysis_slot.acquire(blocking=False):
        response = JsonResponse(
            {"error": "An analysis is already running. Please try again shortly."},
            status=429,
        )
        response["Retry-After"] = "5"
        return response
    try:
        return JsonResponse(analyze_input())
    except (InvalidPGNError, InvalidPositionError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    except ConfigurationError:
        return JsonResponse(
            {"error": "Engine configuration is invalid. Check the server settings."},
            status=503,
        )
    except StockfishEngineError:
        return JsonResponse(
            {"error": "Stockfish is unavailable. Check its installation and settings."},
            status=503,
        )
    finally:
        _analysis_slot.release()
