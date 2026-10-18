"""Provider contract tests using only injected, spec-constrained HTTP doubles."""

import traceback
from unittest.mock import Mock

import chess
import pytest
import requests

from chess_analyzer import stockfish_client
from chess_analyzer.models import PositionEvaluation, StockfishAPIError
from chess_analyzer.stockfish_client import StockfishOnlineClient


@pytest.fixture
def http(settings):
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.json.return_value = {
        "success": True,
        "evaluation": 0.25,
        "mate": None,
        "bestmove": "bestmove e2e4 ponder e7e5",
    }
    session = Mock(spec=requests.Session)
    session.get.return_value = response
    return StockfishOnlineClient(settings, session=session), session, response


def test_exact_request_contract_and_response_cleanup(http, settings):
    client, session, response = http
    evaluation = client.evaluate(chess.STARTING_FEN)
    assert client.settings is settings
    session.get.assert_called_once_with(
        "https://stockfish.online/api/s/v2.php",
        params={
            "fen": chess.STARTING_FEN,
            "depth": 9,
            "key": settings.stockfish_api_key,
        },
        timeout=4.25,
        allow_redirects=False,
    )
    assert evaluation == PositionEvaluation(cp=25, best_move_uci="e2e4")
    response.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("score", "cp"),
    [(0, 0), (1, 100), (-2, -200), (0.29, 29), (1.005, 101), (-1.005, -101)],
)
def test_pawn_scores_use_decimal_half_up_rounding(http, score, cp):
    client, _, response = http
    response.json.return_value["evaluation"] = score
    assert client.evaluate(chess.STARTING_FEN).cp == cp


def test_eval_compatibility_fallback(http):
    client, _, response = http
    payload = response.json.return_value
    del payload["evaluation"]
    payload["eval"] = -0.75
    assert client.evaluate(chess.STARTING_FEN).cp == -75


def test_evaluation_field_takes_precedence_over_eval(http):
    client, _, response = http
    response.json.return_value["eval"] = -99
    assert client.evaluate(chess.STARTING_FEN).cp == 25


@pytest.mark.parametrize("mate", [1, 7, -1, -8])
def test_signed_mate_scores_remain_mates(http, mate):
    client, _, response = http
    response.json.return_value.update(evaluation=None, mate=mate)
    assert client.evaluate(chess.STARTING_FEN) == PositionEvaluation(
        mate=mate, best_move_uci="e2e4"
    )


@pytest.mark.parametrize(
    ("mate", "evaluation"),
    [(0, None), (True, None), (False, None), (1.0, None), ("2", None), (2, 0.5)],
)
def test_invalid_or_conflicting_mate_scores_are_rejected(http, mate, evaluation):
    client, _, response = http
    response.json.return_value.update(mate=mate, evaluation=evaluation)
    with pytest.raises(StockfishAPIError, match="mate score"):
        client.evaluate(chess.STARTING_FEN)
    response.close.assert_called_once_with()


@pytest.mark.parametrize(
    "score",
    [None, True, False, "0.25", [], {}, float("nan"), float("inf"), -float("inf")],
)
def test_invalid_numeric_score_is_rejected(http, score):
    client, _, response = http
    response.json.return_value["evaluation"] = score
    with pytest.raises(StockfishAPIError, match="score"):
        client.evaluate(chess.STARTING_FEN)
    response.close.assert_called_once_with()


def test_missing_numeric_score_is_rejected(http):
    client, _, response = http
    del response.json.return_value["evaluation"]
    with pytest.raises(StockfishAPIError, match="score"):
        client.evaluate(chess.STARTING_FEN)


@pytest.mark.parametrize("payload", [None, [], "body", 1, {}, {"success": 1}])
def test_malformed_payload_is_rejected(http, payload):
    client, _, response = http
    response.json.return_value = payload
    with pytest.raises(StockfishAPIError):
        client.evaluate(chess.STARTING_FEN)
    response.close.assert_called_once_with()


@pytest.mark.parametrize(
    "move",
    [
        None,
        123,
        "",
        "e2e4",
        "bestmove",
        "move e2e4",
        "bestmove nope",
        "bestmove e2e5",
        "bestmove a7a6",
        "bestmove 0000",
        "bestmove (none)",
    ],
)
def test_missing_malformed_or_illegal_bestmove_is_rejected(http, move):
    client, _, response = http
    response.json.return_value["bestmove"] = move
    with pytest.raises(StockfishAPIError, match="best move"):
        client.evaluate(chess.STARTING_FEN)
    response.close.assert_called_once_with()


def test_absent_bestmove_is_rejected(http):
    client, _, response = http
    del response.json.return_value["bestmove"]
    with pytest.raises(StockfishAPIError, match="best move"):
        client.evaluate(chess.STARTING_FEN)


@pytest.mark.parametrize("status", [199, 301, 302, 307, 400, 401, 429, 500, 503])
def test_http_errors_and_redirects_are_not_parsed_or_retried(http, status):
    client, session, response = http
    response.status_code = status
    with pytest.raises(StockfishAPIError, match=f"HTTP {status}"):
        client.evaluate(chess.STARTING_FEN)
    session.get.assert_called_once()
    response.json.assert_not_called()
    response.close.assert_called_once_with()


def test_invalid_json_is_wrapped_and_response_closed(http):
    client, _, response = http
    response.json.side_effect = ValueError("raw-provider-body")
    with pytest.raises(StockfishAPIError, match="invalid JSON"):
        client.evaluate(chess.STARTING_FEN)
    response.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("exception_type", "message"),
    [
        (requests.Timeout, "timed out"),
        (requests.ConnectionError, "Unable to contact"),
        (requests.RequestException, "Unable to contact"),
    ],
)
def test_transport_errors_are_sanitized_and_not_retried(http, exception_type, message):
    client, session, response = http
    session.get.side_effect = exception_type("raw-credential-bearing-url")
    with pytest.raises(StockfishAPIError, match=message):
        client.evaluate(chess.STARTING_FEN)
    session.get.assert_called_once()
    response.close.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "connection", "status", "json", "body"])
def test_formatted_traceback_excludes_key_and_untrusted_details(
    http, settings, failure
):
    client, session, response = http
    raw = (
        "RAW-PROVIDER-OR-EXCEPTION "
        f"https://example.invalid/?key={settings.stockfish_api_key}"
    )
    if failure == "timeout":
        session.get.side_effect = requests.Timeout(raw)
    elif failure == "connection":
        session.get.side_effect = requests.ConnectionError(raw)
    elif failure == "status":
        response.status_code = 403
        response.text = raw
    elif failure == "json":
        response.json.side_effect = ValueError(raw)
    else:
        response.json.return_value = {"success": False, "error": raw}
    with pytest.raises(StockfishAPIError) as error:
        client.evaluate(chess.STARTING_FEN)
    formatted = "".join(traceback.format_exception(error.value))
    assert settings.stockfish_api_key not in formatted
    assert "RAW-PROVIDER-OR-EXCEPTION" not in formatted
    assert "https://example.invalid" not in formatted


@pytest.mark.parametrize("fen", ["not a fen", "8/8/8/8/8/8/8/8 w - - 0 1"])
def test_invalid_fen_is_rejected_before_http(http, fen):
    client, session, _ = http
    with pytest.raises(ValueError):
        client.evaluate(fen)
    session.get.assert_not_called()


@pytest.mark.parametrize(
    ("fen", "expected"),
    [
        (
            "7k/6Q1/5K2/8/8/8/8/8 b - - 0 1",
            PositionEvaluation(mate=0, terminal_result="1-0"),
        ),
        (
            "8/8/8/8/8/5k2/6q1/7K w - - 0 1",
            PositionEvaluation(mate=0, terminal_result="0-1"),
        ),
        (
            "7k/5K2/6Q1/8/8/8/8/8 b - - 0 1",
            PositionEvaluation(cp=0, terminal_result="1/2-1/2"),
        ),
        (
            "7k/8/8/8/8/8/8/K7 w - - 0 1",
            PositionEvaluation(cp=0, terminal_result="1/2-1/2"),
        ),
        (
            "7k/8/8/8/8/8/R7/K7 w - - 150 76",
            PositionEvaluation(cp=0, terminal_result="1/2-1/2"),
        ),
    ],
)
def test_automatic_terminal_positions_are_resolved_locally(http, fen, expected):
    client, session, _ = http
    assert chess.Board(fen).is_valid()
    assert client.evaluate(fen) == expected
    session.get.assert_not_called()


def test_injected_session_is_never_closed_even_on_context_exception(http):
    client, session, _ = http
    with pytest.raises(RuntimeError, match="caller failure"), client as entered:
        assert entered is client
        raise RuntimeError("caller failure")
    client.close()
    session.close.assert_not_called()


@pytest.mark.parametrize("raise_in_context", [False, True])
def test_owned_session_is_closed_on_context_exit(
    monkeypatch, settings, raise_in_context
):
    session = Mock(spec=requests.Session)
    factory = Mock(return_value=session)
    monkeypatch.setattr(stockfish_client.requests, "Session", factory)
    if raise_in_context:
        with pytest.raises(RuntimeError), StockfishOnlineClient(settings):
            raise RuntimeError("caller failure")
    else:
        with StockfishOnlineClient(settings) as client:
            assert client.settings is settings
    factory.assert_called_once_with()
    session.close.assert_called_once_with()


def test_owned_session_can_be_closed_explicitly(monkeypatch, settings):
    session = Mock(spec=requests.Session)
    monkeypatch.setattr(
        stockfish_client.requests, "Session", Mock(return_value=session)
    )
    StockfishOnlineClient(settings).close()
    session.close.assert_called_once_with()
