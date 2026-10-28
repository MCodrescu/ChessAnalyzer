"""Game-review page and analysis endpoint."""

from django.http import JsonResponse
from django.urls import path
from django.views.decorators.http import require_safe

from chess_analyzer.web import views


@require_safe
def health_check(request):
    """Report web readiness without allocating an engine or calling upstreams."""
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response


urlpatterns = [
    path("healthz/", health_check, name="health-check"),
    path("", views.index, name="review"),
    path("api/analyze/", views.analyze, name="analyze"),
    path("api/position/", views.position_analysis, name="position-analysis"),
    path("api/ratings/", views.rating_submit, name="rating-submit"),
    path("api/ratings/<slug:job_id>/", views.rating_status, name="rating-status"),
    path("api/chesscom/games/", views.chesscom_games, name="chesscom-games"),
]
