/** Lichess accuracy algorithm applied to this app's local engine evaluations.
 * Verified against lila revision 06ee34552b24fa1a52e749d92fbc3a1ad37a5afb:
 * https://github.com/lichess-org/lila/blob/06ee34552b24fa1a52e749d92fbc3a1ad37a5afb/modules/analyse/src/main/AccuracyPercent.scala
 * WinPercent caps CP at ±1000; scalalib.Maths uses population deviation and
 * floors harmonic-mean inputs at 1. Engine settings can differ from lichess.org.
 */
export function whiteWinPercent(evaluation) {
  if (!evaluation) return null;
  let cp = evaluation.cp;
  if (evaluation.terminal_result === '1-0') cp = 1000;
  else if (evaluation.terminal_result === '0-1') cp = -1000;
  else if (evaluation.terminal_result === '1/2-1/2') cp = 0;
  else if (Number.isFinite(evaluation.mate) && evaluation.mate !== 0) cp = evaluation.mate > 0 ? 1000 : -1000;
  if (!Number.isFinite(cp)) return null;
  cp = Math.max(-1000, Math.min(1000, cp));
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
}

function accuracyFromWinPercents(before, after) {
  if (before === null || after === null) return null;
  if (after >= before) return 100;
  const raw = 103.1668100711649 * Math.exp(-0.04354415386753951 * (before - after)) - 3.166924740191411;
  return Math.max(0, Math.min(100, raw + 1));
}

/** Estimate one move's accuracy from the mover's loss of winning chances. */
export function moveAccuracy(move) {
  const before = whiteWinPercent(move.evaluation_before);
  const after = whiteWinPercent(move.evaluation_after);
  return move.player === 'white'
    ? accuracyFromWinPercents(before, after)
    : accuracyFromWinPercents(after, before);
}

/** Lichess game accuracy: mean of volatility-weighted and harmonic means.
 * Use one shared timeline (initial evaluation + every actual post-move eval).
 * Missing windows are skipped without changing the alternating move colors.
 * Like Lichess, a game needs scored moves for both colors to have game accuracy.
 */
export function gameAccuracy(moves) {
  const result = { white: { accuracy: null, count: 0 }, black: { accuracy: null, count: 0 } };
  if (!moves.length) return result;
  const chances = [moves[0].evaluation_before, ...moves.map((move) => move.evaluation_after)].map(whiteWinPercent);
  const windowSize = Math.max(2, Math.min(8, Math.floor(moves.length / 10)));
  const samples = { white: [], black: [] };
  for (let index = 0; index < moves.length; index++) {
    // Lichess repeats the first full window windowSize - 2 times before sliding.
    const start = Math.max(0, index - windowSize + 2);
    const window = chances.slice(start, start + windowSize);
    if (window.some((chance) => chance === null)) continue;
    const mean = window.reduce((sum, chance) => sum + chance, 0) / window.length;
    const deviation = Math.sqrt(window.reduce((sum, chance) => sum + (chance - mean) ** 2, 0) / window.length);
    const weight = Math.max(0.5, Math.min(12, deviation));
    const player = index % 2 === 0 ? moves[0].player : moves[0].player === 'white' ? 'black' : 'white';
    const score = player === 'white'
      ? accuracyFromWinPercents(chances[index], chances[index + 1])
      : accuracyFromWinPercents(chances[index + 1], chances[index]);
    if (score !== null) samples[player].push({ score, weight });
  }
  for (const player of ['white', 'black']) {
    result[player].count = samples[player].length;
  }
  if (!samples.white.length || !samples.black.length) return result;
  for (const player of ['white', 'black']) {
    const scores = samples[player];
    const weightSum = scores.reduce((sum, { weight }) => sum + weight, 0);
    const weighted = scores.reduce((sum, { score, weight }) => sum + score * weight, 0) / weightSum;
    const harmonic = scores.length / scores.reduce((sum, { score }) => sum + 1 / Math.max(1, score), 0);
    result[player].accuracy = (weighted + harmonic) / 2;
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