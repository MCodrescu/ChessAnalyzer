"""Game-review page and analysis endpoint."""

from django.urls import path

from chess_analyzer.web import views

urlpatterns = [
    path("", views.index, name="review"),
    path("api/analyze/", views.analyze, name="analyze"),
    path("api/chesscom/games/", views.chesscom_games, name="chesscom-games"),
]
