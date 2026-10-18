"""CSRF-protected local analysis HTTP endpoints."""

import json
from threading import BoundedSemaphore

from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from chess_analyzer.config import ConfigurationError
from chess_analyzer.models import InvalidPGNError, StockfishEngineError
from chess_analyzer.web.services import analyze_pgn

# One CPU-intensive job per web process. Multi-worker deployments need a queue
# with a global concurrency limit, not additional unconstrained web workers.
_analysis_slot = BoundedSemaphore(1)


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    """Render the PGN import form and Chessground review workspace."""
    return render(request, "review/index.html")


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
    if not _analysis_slot.acquire(blocking=False):
        response = JsonResponse(
            {"error": "An analysis is already running. Please try again shortly."},
            status=429,
        )
        response["Retry-After"] = "5"
        return response
    try:
        return JsonResponse(analyze_pgn(data["pgn"]))
    except InvalidPGNError as error:
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
