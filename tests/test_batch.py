"""Ordered batch integration preserves serial scoring and terminal history."""

import chess
import pytest

from chess_analyzer.analyzer import PGNAnalyzer
from chess_analyzer.models import PositionEvaluation, StockfishEngineError


@pytest.mark.parametrize(
    "pgn",
    [
        "1. e4 e5 2. Nf3 Nc6 *",
        "1. f3 e5 2. g4 Qh4# 0-1",
        "1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8 "
        "5. Nf3 Nf6 6. Ng1 Ng8 7. Nf3 Nf6 8. Ng1 Ng8 1/2-1/2",
    ],
)
def test_batch_matches_serial_including_terminal_history(settings, pgn):
    class Serial:
        def __init__(self):
            self.settings = settings
            self.calls = []

        def evaluate(self, fen):
            self.calls.append(fen)
            return PositionEvaluation(
                cp=10, best_move_uci=next(iter(chess.Board(fen).legal_moves)).uci()
            )

    class Batch(Serial):
        def evaluate_many(self, fens):
            return [self.evaluate(fen) for fen in fens]

    serial, batch = Serial(), Batch()
    assert PGNAnalyzer(batch).analyze(pgn) == PGNAnalyzer(serial).analyze(pgn)
    assert batch.calls == serial.calls


def test_incomplete_batch_is_rejected_before_scoring(settings):
    class Incomplete:
        def __init__(self):
            self.settings = settings

        def evaluate(self, fen):
            pytest.fail("Batch evaluator must not fall back to single evaluation.")

        def evaluate_many(self, fens):
            return []

    with pytest.raises(StockfishEngineError, match="incomplete"):
        PGNAnalyzer(Incomplete()).analyze("1. e4 *")
