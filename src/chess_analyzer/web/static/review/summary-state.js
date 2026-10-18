/** Local estimates, not Chess.com or Lichess game accuracy ratings.
 * Move formulas: https://lichess.org/page/accuracy
 * Game scores here use a simple arithmetic mean, not Lichess's weighting.
 */
export function whiteWinPercent(evaluation) {
  if (!evaluation) return null;
  if (evaluation.terminal_result === '1-0') return 100;
  if (evaluation.terminal_result === '0-1') return 0;
  if (evaluation.terminal_result === '1/2-1/2') return 50;
  if (Number.isFinite(evaluation.mate) && evaluation.mate !== 0) return evaluation.mate > 0 ? 100 : 0;
  if (!Number.isFinite(evaluation.cp)) return null;
  return 100 / (1 + Math.exp(-0.00368208 * evaluation.cp));
}

/** Estimate one move's accuracy from the mover's loss of winning chances. */
export function moveAccuracy(move) {
  const before = whiteWinPercent(move.evaluation_before);
  const after = whiteWinPercent(move.evaluation_after);
  if (before === null || after === null) return null;
  const loss = Math.max(0, (before - after) * (move.player === 'white' ? 1 : -1));
  // Independent searches may disagree slightly even for the engine's best move.
  if (move.is_best_move || loss === 0) return 100;
  return Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * loss) - 3.1669));
}

/** Mean move accuracy per color; unscored moves and absent players have no score. */
export function gameAccuracy(moves) {
  const result = {};
  for (const player of ['white', 'black']) {
    const scores = moves.filter((move) => move.player === player).map(moveAccuracy).filter((score) => score !== null);
    result[player] = {
      accuracy: scores.length ? scores.reduce((sum, score) => sum + score, 0) / scores.length : null,
      count: scores.length,
    };
  }
  return result;
}

/** White-relative graph score, capped at ±10 pawns; mates use the graph edges. */
export function graphScore(evaluation) {
  if (!evaluation) return null;
  if (evaluation.terminal_result === '1-0') return 10;
  if (evaluation.terminal_result === '0-1') return -10;
  if (evaluation.terminal_result === '1/2-1/2') return 0;
  if (Number.isFinite(evaluation.mate) && evaluation.mate !== 0) return evaluation.mate > 0 ? 10 : -10;
  if (!Number.isFinite(evaluation.cp)) return null;
  return Math.max(-10, Math.min(10, evaluation.cp / 100));
}

/** Include the initial position, then every actual move (never best-line previews). */
export function evaluationSeries(moves) {
  if (!moves.length) return [];
  return [
    { label: 'Start', evaluation: moves[0].evaluation_before },
    ...moves.map((move) => ({
      label: `${move.fullmove_number}${move.player === 'white' ? '.' : '…'} ${move.played_move_san}`,
      evaluation: move.evaluation_after,
    })),
  ].map((point) => ({ ...point, score: graphScore(point.evaluation) }));
}