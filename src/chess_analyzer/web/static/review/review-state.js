/** Pure presentation helpers shared with deterministic Node tests. */
export function formatEvaluation(evaluation) {
  if (!evaluation) return '—';
  if (evaluation.terminal_result) return evaluation.terminal_result;
  if (evaluation.mate !== null) return `M${evaluation.mate > 0 ? '+' : ''}${evaluation.mate}`;
  return `${evaluation.cp >= 0 ? '+' : ''}${(evaluation.cp / 100).toFixed(2)}`;
}

export function moveSquares(uci) {
  return [uci.slice(0, 2), uci.slice(2, 4)];
}

export function positionFor(move, preview) {
  if (preview === 'played') return { fen: move.fen_after, lastMove: moveSquares(move.played_move_uci), shapes: [] };
  if (preview === 'best') return { fen: move.best_fen, lastMove: moveSquares(move.best_move_uci), shapes: [] };
  const [orig, dest] = moveSquares(move.best_move_uci);
  const shapes = [{ orig, dest, brush: 'green' }];
  if (!move.is_best_move) {
    const [playedOrig, playedDest] = moveSquares(move.played_move_uci);
    shapes.push({ orig: playedOrig, dest: playedDest, brush: 'blue' });
  }
  return { fen: move.fen_before, lastMove: undefined, shapes };
}