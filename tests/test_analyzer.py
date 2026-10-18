"""Observable replay and scoring contracts with deterministic FEN-aware doubles."""

from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock

import chess
import pytest

from chess_analyzer.analyzer import PGNAnalyzer
from chess_analyzer.models import (
    InvalidPGNError,
    PositionEvaluation,
    StockfishEngineError,
)


class FakeEvaluator:
    """Return prepared scores by FEN, rejecting unplanned or terminal requests."""

    def __init__(self, settings, evaluations):
        self.settings = settings
        self.evaluations = evaluations
        self.calls = []

    def evaluate(self, fen):
        assert not chess.Board(fen).is_game_over(claim_draw=False)
        assert fen in self.evaluations, f"Unexpected position: {fen}"
        self.calls.append(fen)
        return self.evaluations[fen]


@pytest.fixture
def make_evaluator(settings):
    def make(sans=(), *, scores=None, best_moves=None, fen=chess.STARTING_FEN):
        """Build an independent legal replay; optionally override scores/moves."""
        board = chess.Board(fen)
        boards = [board.copy()]
        for san in sans:
            board.push_san(san)
            boards.append(board.copy())
        if scores is None:
            scores = [0] * len(boards)
        assert len(scores) == len(boards)
        best_moves = best_moves or {}
        evaluations = {}
        for index, (position, score) in enumerate(zip(boards, scores, strict=True)):
            legal = list(position.legal_moves)
            best = best_moves.get(index, legal[0].uci() if legal else None)
            evaluation = (
                score
                if isinstance(score, PositionEvaluation)
                else PositionEvaluation(cp=score)
            )
            evaluations[position.fen()] = replace(evaluation, best_move_uci=best)
        return FakeEvaluator(settings, evaluations)

    return make


def setup_pgn(fen, movetext, *, result="*", extra_headers=""):
    return (
        f'[SetUp "1"]\n[FEN "{fen}"]\n[Result "{result}"]\n'
        f"{extra_headers}\n{movetext} {result}"
    )


def test_white_and_black_loss_signs_and_result_metadata(make_evaluator, settings):
    client = make_evaluator(
        ["e4", "e5"],
        scores=[100, 25, 80],
        best_moves={0: "d2d4", 1: "c7c5"},
    )
    result = PGNAnalyzer(client).analyze('[Event "Unit test"]\n\n1. e4 e5 *')
    assert result.headers["Event"] == "Unit test"
    assert result.analysis_depth == settings.analysis_depth
    assert result.analysis_time_seconds == settings.analysis_time_seconds
    assert isinstance(result.moves, tuple)
    white, black = result.moves
    assert (white.player, white.ply, white.fullmove_number) == ("white", 1, 1)
    assert (black.player, black.ply, black.fullmove_number) == ("black", 2, 1)
    assert (white.cp_delta, white.estimated_cp_loss) == (75, 75)
    assert (black.cp_delta, black.estimated_cp_loss) == (55, 55)
    assert (white.played_move_san, white.played_move_uci) == ("e4", "e2e4")
    assert (white.best_move_san, white.best_move_uci) == ("d4", "d2d4")
    assert (black.best_move_san, black.best_move_uci) == ("c5", "c7c5")
    assert not white.is_best_move
    assert not black.is_best_move


def test_n_plus_one_requests_and_before_after_object_reuse(make_evaluator):
    client = make_evaluator(["e4", "e5", "Nf3", "Nc6"], scores=[1, 2, 3, 4, 5])
    result = PGNAnalyzer(client).analyze("1. e4 e5 2. Nf3 Nc6 *")
    assert len(client.calls) == len(result.moves) + 1 == 5
    expected_fens = [result.moves[0].fen_before] + [m.fen_after for m in result.moves]
    assert client.calls == expected_fens
    for move in result.moves:
        assert move.evaluation_before is client.evaluations[move.fen_before]
        assert move.evaluation_after is client.evaluations[move.fen_after]
    for previous, current in zip(result.moves[:-1], result.moves[1:], strict=True):
        assert previous.fen_after == current.fen_before
        assert previous.evaluation_after is current.evaluation_before


@pytest.mark.parametrize(
    ("scores", "best_moves", "expected_deltas", "expected_best"),
    [
        ([100, 25, 80], {0: "e2e4", 1: "e7e5"}, [75, 55], True),
        ([25, 100, 50], {0: "d2d4", 1: "c7c5"}, [-75, -50], False),
        ([0, 0, 0], {0: "d2d4", 1: "c7c5"}, [0, 0], False),
    ],
    ids=["best-move-keeps-raw-delta", "search-noise-clamped", "equal-scores"],
)
def test_zero_loss_does_not_discard_raw_signed_delta(
    make_evaluator, scores, best_moves, expected_deltas, expected_best
):
    client = make_evaluator(["e4", "e5"], scores=scores, best_moves=best_moves)
    moves = PGNAnalyzer(client).analyze("1. e4 e5 *").moves
    assert [move.cp_delta for move in moves] == expected_deltas
    assert [move.estimated_cp_loss for move in moves] == [0, 0]
    assert [move.is_best_move for move in moves] == [expected_best, expected_best]


def test_fen_start_respects_black_turn_and_fullmove_number(make_evaluator):
    board = chess.Board()
    board.push_san("e4")
    board.fullmove_number = 23
    fen = board.fen()
    client = make_evaluator(
        ["e5", "Nf3"],
        fen=fen,
        scores=[-50, 25, -5],
        best_moves={0: "c7c5", 1: "b1c3"},
    )
    result = PGNAnalyzer(client).analyze(setup_pgn(fen, "23... e5 24. Nf3"))
    black, white = result.moves
    assert (black.player, black.fullmove_number, black.ply) == ("black", 23, 1)
    assert (white.player, white.fullmove_number, white.ply) == ("white", 24, 2)
    assert black.fen_before == fen
    assert black.cp_delta == 75
    assert white.cp_delta == 30
    assert client.calls[0] == fen


def test_comments_nags_and_legal_variations_do_not_add_evaluations(make_evaluator):
    client = make_evaluator(["e4", "e5", "Nf3"])
    pgn = (
        '[Event "Mainline only"]\n\n'
        "1. e4 $1 {not a move: Qh5} (1. d4 d5 (1... Nf6)) "
        "e5 ; ignore this comment\n2. Nf3 *"
    )
    result = PGNAnalyzer(client).analyze(pgn)
    assert [move.played_move_uci for move in result.moves] == ["e2e4", "e7e5", "g1f3"]
    assert len(client.calls) == 4


@pytest.mark.parametrize("pgn", ['[Event "No moves"]', '[Event "No moves"]\n\n*', "*"])
def test_valid_game_without_moves_makes_no_requests(make_evaluator, pgn):
    client = make_evaluator()
    result = PGNAnalyzer(client).analyze(pgn)
    assert result.moves == ()
    assert client.calls == []


@pytest.mark.parametrize(
    "pgn",
    [
        None,
        123,
        b"1. e4 *",
        "",
        " \n\t",
        "this is not a PGN",
        "1. e4 e5 2. Bh6 *",
        "1. e4 e5 2. e5 *",
        "1. -- *",
        "1. e4 *\n\n1. d4 *",
        '[Event "First"]\n\n*\n\n[Event "Second"]\n\n*',
        '[Variant "Atomic"]\n\n*',
        '[Variant "Antichess"]\n\n*',
        '[Variant "Chess960"]\n\n*',
        '[Variant "UnknownVariant"]\n\n*',
        setup_pgn("not a fen", ""),
        setup_pgn("8/8/8/8/8/8/8/8 w - - 0 1", ""),
        setup_pgn("7k/8/8/8/8/8/8/K6P w - - 0 1", ""),
    ],
    ids=[
        "none",
        "integer",
        "bytes",
        "empty",
        "whitespace",
        "unparseable-text",
        "illegal-bishop",
        "illegal-pawn",
        "null-move",
        "multiple-movetext-games",
        "multiple-header-games",
        "atomic",
        "antichess",
        "chess960",
        "unknown-variant",
        "malformed-fen",
        "missing-kings",
        "pawn-on-back-rank",
    ],
)
def test_invalid_input_is_rejected_before_any_evaluation(make_evaluator, pgn):
    client = make_evaluator()
    with pytest.raises(InvalidPGNError):
        PGNAnalyzer(client).analyze(pgn)
    assert client.calls == []


@pytest.mark.parametrize(
    ("fen", "san", "uci"),
    [
        ("7k/P7/8/8/8/8/8/7K w - - 0 1", "a8=Q+", "a7a8q"),
        ("7k/P7/8/8/8/8/8/7K w - - 0 1", "a8=N", "a7a8n"),
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "O-O", "e1g1"),
        ("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", "O-O-O", "e8c8"),
        ("7k/8/8/3pP3/8/8/8/K7 w - d6 0 1", "exd6", "e5d6"),
    ],
    ids=[
        "promotion",
        "underpromotion",
        "white-castling",
        "black-castling",
        "en-passant",
    ],
)
def test_special_moves_preserve_played_and_best_san_uci(make_evaluator, fen, san, uci):
    client = make_evaluator([san], fen=fen, best_moves={0: uci})
    result = PGNAnalyzer(client).analyze(setup_pgn(fen, san))
    (move,) = result.moves
    assert move.played_move_san == move.best_move_san == san
    assert move.played_move_uci == move.best_move_uci == uci
    assert move.is_best_move
    board = chess.Board(fen)
    board.push_uci(uci)
    assert move.fen_after == board.fen()


@pytest.mark.parametrize(
    "scores",
    [
        [PositionEvaluation(mate=3), 50],
        [20, PositionEvaluation(mate=-2)],
        [PositionEvaluation(mate=-4), PositionEvaluation(mate=2)],
    ],
    ids=["mate-to-cp", "cp-to-mate", "signed-mate-to-mate"],
)
def test_mate_transitions_have_no_artificial_centipawn_loss(make_evaluator, scores):
    client = make_evaluator(["e4"], scores=scores, best_moves={0: "e2e4"})
    (move,) = PGNAnalyzer(client).analyze("1. e4 *").moves
    assert move.cp_delta is None
    assert move.estimated_cp_loss is None
    assert move.evaluation_before.cp == client.evaluations[move.fen_before].cp
    assert move.evaluation_after.mate == client.evaluations[move.fen_after].mate


def test_checkmate_mate_zero_is_resolved_locally_and_loss_is_none(make_evaluator):
    client = make_evaluator(["f3", "e5", "g4", "Qh4#"])
    result = PGNAnalyzer(client).analyze("1. f3 e5 2. g4 Qh4# 0-1")
    last = result.moves[-1]
    assert last.played_move_san == "Qh4#"
    assert last.evaluation_after == PositionEvaluation(mate=0, terminal_result="0-1")
    assert last.cp_delta is None
    assert last.estimated_cp_loss is None
    assert len(client.calls) == 4
    assert last.fen_after not in client.calls


@pytest.mark.parametrize(
    ("fen", "san", "termination"),
    [
        ("7k/5K2/8/6Q1/8/8/8/8 w - - 0 1", "Qg6", chess.Termination.STALEMATE),
        (
            "7k/8/8/8/8/8/1r6/K7 w - - 0 1",
            "Kxb2",
            chess.Termination.INSUFFICIENT_MATERIAL,
        ),
        ("7k/8/8/8/8/8/R7/K7 w - - 149 76", "Ra3", chess.Termination.SEVENTYFIVE_MOVES),
    ],
    ids=["stalemate", "insufficient-material", "seventy-five-moves"],
)
def test_automatic_draws_are_evaluated_locally(make_evaluator, fen, san, termination):
    board = chess.Board(fen)
    assert board.outcome(claim_draw=False) is None
    board.push_san(san)
    assert board.outcome(claim_draw=False).termination == termination
    client = make_evaluator([san], fen=fen, scores=[125, 999])
    (move,) = PGNAnalyzer(client).analyze(setup_pgn(fen, san, result="1/2-1/2")).moves
    assert move.evaluation_after == PositionEvaluation(cp=0, terminal_result="1/2-1/2")
    assert client.calls == [fen]
    assert move.cp_delta == 125


def repetition_pgn(cycles, *, extra_move=""):
    pairs = []
    for cycle in range(cycles):
        pairs.append(f"{cycle * 2 + 1}. Nf3 Nf6 {cycle * 2 + 2}. Ng1 Ng8")
    return " ".join(pairs) + f" {extra_move} *"


def test_fivefold_repetition_uses_history_and_skips_final_request(make_evaluator):
    sans = ["Nf3", "Nf6", "Ng1", "Ng8"] * 4
    client = make_evaluator(sans)
    result = PGNAnalyzer(client).analyze(repetition_pgn(4))
    assert len(result.moves) == 16
    assert len(client.calls) == 16
    last = result.moves[-1]
    assert last.evaluation_after == PositionEvaluation(cp=0, terminal_result="1/2-1/2")
    # The final FEN alone cannot encode the repetition that ended this game.
    assert not chess.Board(last.fen_after).is_game_over(claim_draw=False)
    assert last.fen_after not in client.calls


def test_claimable_threefold_draw_is_not_automatic(make_evaluator):
    sans = ["Nf3", "Nf6", "Ng1", "Ng8"] * 2
    client = make_evaluator(sans)
    result = PGNAnalyzer(client).analyze(repetition_pgn(2))
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    assert board.can_claim_threefold_repetition()
    assert not board.is_game_over(claim_draw=False)
    assert len(client.calls) == 9
    assert result.moves[-1].evaluation_after.terminal_result is None


def test_claimable_fifty_move_draw_is_not_automatic(make_evaluator):
    fen = "7k/8/8/8/8/8/R7/K7 w - - 100 51"
    assert chess.Board(fen).can_claim_fifty_moves()
    client = make_evaluator(["Ra3"], fen=fen)
    (move,) = PGNAnalyzer(client).analyze(setup_pgn(fen, "51. Ra3")).moves
    assert len(client.calls) == 2
    assert move.evaluation_before.terminal_result is None
    assert move.evaluation_after.terminal_result is None


@pytest.mark.parametrize(
    "pgn",
    [
        repetition_pgn(4, extra_move="9. Nf3"),
        setup_pgn("7k/8/8/8/8/8/R7/K7 w - - 149 76", "76. Ra3 Kg8"),
        setup_pgn("7k/8/8/8/8/8/8/K7 w - - 0 1", "1. Kb1"),
    ],
    ids=["after-fivefold", "after-seventy-five-moves", "after-insufficient-material"],
)
def test_moves_after_automatic_draw_rejected_before_evaluation(make_evaluator, pgn):
    client = make_evaluator()
    with pytest.raises(InvalidPGNError, match="automatic game end"):
        PGNAnalyzer(client).analyze(pgn)
    assert client.calls == []


@pytest.mark.parametrize("result", ["1-0", "0-1", "1/2-1/2"])
def test_recorded_result_does_not_force_a_terminal_evaluation(make_evaluator, result):
    client = make_evaluator(["e4"], scores=[10, 20])
    game = PGNAnalyzer(client).analyze(f'[Result "{result}"]\n\n1. e4 {result}')
    assert game.headers["Result"] == result
    assert len(client.calls) == 2
    assert game.moves[-1].evaluation_after.cp == 20
    assert game.moves[-1].evaluation_after.terminal_result is None


@pytest.mark.parametrize("failure_index", [0, 1, 2])
def test_engine_failures_propagate_without_partial_result(
    make_evaluator, failure_index
):
    client = make_evaluator(["e4", "e5"])
    failure = StockfishEngineError("engine failure")
    responses = list(client.evaluations.values())[:failure_index] + [failure]
    client.evaluate = Mock(side_effect=responses)
    with pytest.raises(StockfishEngineError) as error:
        PGNAnalyzer(client).analyze("1. e4 e5 *")
    assert error.value is failure
    assert client.evaluate.call_count == failure_index + 1


@pytest.mark.parametrize("best_move", [None, "", "not-uci", "0000", "e2e5", "a7a6"])
def test_invalid_evaluator_bestmove_is_not_silently_used(make_evaluator, best_move):
    client = make_evaluator(["e4"], best_moves={0: best_move})
    with pytest.raises(StockfishEngineError, match="best move"):
        PGNAnalyzer(client).analyze("1. e4 *")
    assert client.calls == [chess.STARTING_FEN]


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"cp": 0, "mate": 1},
        {"cp": True},
        {"mate": False},
        {"cp": 1.0},
        {"mate": "2"},
    ],
)
def test_position_evaluation_requires_exactly_one_integer_score(kwargs):
    with pytest.raises(ValueError):
        PositionEvaluation(**kwargs)


@pytest.mark.parametrize("kwargs", [{"cp": 0}, {"cp": -25}, {"mate": -3}, {"mate": 0}])
def test_position_evaluation_accepts_zero_and_signed_scores_and_is_frozen(kwargs):
    evaluation = PositionEvaluation(**kwargs)
    for name, value in kwargs.items():
        assert getattr(evaluation, name) == value
    with pytest.raises(FrozenInstanceError):
        evaluation.cp = 5
