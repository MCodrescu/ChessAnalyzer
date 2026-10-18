import assert from 'node:assert/strict';
import test from 'node:test';
import { evaluationSeries, gameAccuracy, graphScore, moveAccuracy, whiteWinPercent } from '../../src/chess_analyzer/web/static/review/summary-state.js';

const cp = (value) => ({ cp: value, mate: null, terminal_result: null });
const move = (player, before, after) => ({ player, evaluation_before: cp(before), evaluation_after: cp(after) });

function fromCPs(cps, firstPlayer = 'white') {
  return cps.slice(1).map((after, index) => move(
    index % 2 === 0 ? firstPlayer : firstPlayer === 'white' ? 'black' : 'white',
    cps[index], after,
  ));
}

function close(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`);
}

test('winning chances are white-relative, symmetric, and bounded', () => {
  assert.equal(whiteWinPercent(cp(0)), 50);
  assert.ok(Math.abs(whiteWinPercent(cp(100)) - 59.102666) < 0.0001);
  assert.ok(Math.abs(whiteWinPercent(cp(-100)) + whiteWinPercent(cp(100)) - 100) < 1e-10);
  assert.equal(whiteWinPercent(cp(1e9)), whiteWinPercent(cp(1000)));
  assert.equal(whiteWinPercent(cp(-1e9)), whiteWinPercent(cp(-1000)));
  assert.ok(whiteWinPercent(cp(1000)) < 98);
  assert.ok(whiteWinPercent(cp(-1000)) > 2);
});

test('accuracy accounts for mover color and treats improvements as no loss', () => {
  assert.equal(moveAccuracy(move('white', 0, 100)), 100);
  assert.equal(moveAccuracy(move('black', 0, -100)), 100);
  const whiteLoss = moveAccuracy(move('white', 0, -100));
  assert.ok(whiteLoss > 60 && whiteLoss < 70);
  close(whiteLoss, moveAccuracy(move('black', 0, 100)));
  assert.equal(moveAccuracy({ ...move('white', 0, -100), is_best_move: true }), whiteLoss);
  // Current Lichess coefficients plus the one-point uncertainty bonus.
  close(whiteLoss, 103.1668100711649 * Math.exp(-0.04354415386753951 * (50 - whiteWinPercent(cp(-100)))) - 3.166924740191411 + 1);
  assert.equal(moveAccuracy(move('white', 0, -1)), 100);
});

test('forced mates and terminal results use Lichess capped winning chances', () => {
  assert.equal(whiteWinPercent({ cp: null, mate: 3 }), whiteWinPercent(cp(1000)));
  assert.equal(whiteWinPercent({ cp: null, mate: -2 }), whiteWinPercent(cp(-1000)));
  assert.equal(whiteWinPercent({ mate: 0, terminal_result: '0-1' }), whiteWinPercent(cp(-1000)));
  assert.equal(whiteWinPercent({ terminal_result: '1-0' }), whiteWinPercent(cp(1000)));
  assert.equal(whiteWinPercent({ terminal_result: '1/2-1/2' }), 50);
  assert.equal(moveAccuracy({ player: 'white', evaluation_before: { mate: 2 }, evaluation_after: { mate: -2 } }), 0);
  assert.equal(moveAccuracy({ player: 'black', evaluation_before: { mate: -2 }, evaluation_after: { terminal_result: '0-1' } }), 100);
});

test('matches upstream examples: perfect moves followed by a blunder are not averaged away', () => {
  // AccuracyPercentTest.scala cases at lila revision 06ee345; tighter reference
  // values independently calculated from explicit window lists and both means.
  const white = gameAccuracy(fromCPs([15, ...Array(20).fill(15), -900]));
  close(white.white.accuracy, 46.85340283303507);
  assert.equal(white.white.count, 11);
  assert.equal(white.black.accuracy, 100);
  const black = gameAccuracy(fromCPs([15, ...Array(21).fill(15), 900]));
  close(black.black.accuracy, 49.387960289369005);
  assert.equal(black.white.accuracy, 100);
  close(gameAccuracy(fromCPs([15, -900, -900])).white.accuracy, 10.664056896199494);
});

test('matches upstream repeated-loss examples and harmonic floor at zero accuracy', () => {
  for (const [lossCP, expected] of [[-50, 76], [-135, 54], [-435, 20]]) {
    const scores = gameAccuracy(fromCPs([15, ...Array(50).fill([lossCP, 15]).flat()]));
    for (const player of ['white', 'black']) assert.ok(Math.abs(scores[player].accuracy - expected) <= 8);
  }
  const zero = gameAccuracy(fromCPs([1000, -1000, -1000]));
  // Weighted mean 0, harmonic mean 1: Lichess floors harmonic inputs at 1.
  assert.equal(zero.white.accuracy, 0.5);
  assert.equal(zero.black.accuracy, 100);
  assert.equal(gameAccuracy(fromCPs(Array(21).fill(15))).white.accuracy, 100);
});

test('population volatility weights and initial-window alignment match reference boundaries', () => {
  // Low-volatility fixtures avoid the upper weight cap hiding window mistakes.
  const references = [
    [19, 87.78032068453385, 81.41951247412749],
    [20, 87.78032068453385, 82.20816869964403],
    [29, 85.35943046227658, 85.36808695234151],
    [30, 86.91176929649892, 86.95009229013307],
    [79, 92.28366444217869, 91.13993659867684],
    [80, 92.3548479686611, 90.77045608883157],
    [100, 93.16457216850364, 91.95366899751127],
  ];
  for (const [plies, white, black] of references) {
    const cps = [15, ...Array.from({ length: plies }, (_, i) => ((i * i * 17 + i * 43) % 221) - 110)];
    const result = gameAccuracy(fromCPs(cps));
    close(result.white.accuracy, white);
    close(result.black.accuracy, black);
    assert.equal(result.white.count, Math.ceil(plies / 2));
    assert.equal(result.black.count, Math.floor(plies / 2));
    // Black-to-move custom starts retain the same scores under color inversion.
    const inverted = gameAccuracy(fromCPs(cps.map((score) => -score), 'black'));
    close(inverted.black.accuracy, white);
    close(inverted.white.accuracy, black);
  }
});

test('uses actual initial evaluation and one shared timeline, not independent before searches', () => {
  const moves = fromCPs([25, -10, 0]);
  moves[1].evaluation_before = cp(900);
  moves[1].is_best_move = true;
  const scores = gameAccuracy(moves);
  close(scores.white.accuracy, 87.50260278151107);
  close(scores.black.accuracy, 96.94685266933499);
});

test('missing volatility windows are excluded without shifting move colors', () => {
  const scores = gameAccuracy(fromCPs([15, 15, null, 15, 15, 15, 15]));
  assert.deepEqual(scores, { white: { accuracy: 100, count: 2 }, black: { accuracy: 100, count: 2 } });
  const longer = fromCPs(Array(31).fill(15));
  longer[9].evaluation_after = null;
  const result = gameAccuracy(longer);
  assert.deepEqual(result, { white: { accuracy: 100, count: 14 }, black: { accuracy: 100, count: 13 } });
});

test('empty games, one-sided games, and missing evaluations do not fake accuracy', () => {
  assert.deepEqual(gameAccuracy([]), { white: { accuracy: null, count: 0 }, black: { accuracy: null, count: 0 } });
  assert.equal(gameAccuracy([move('black', 0, 0)]).white.accuracy, null);
  assert.equal(gameAccuracy([move('black', 0, 0)]).black.accuracy, null);
  const missingBlack = gameAccuracy(fromCPs([15, 15, null]));
  assert.equal(missingBlack.white.accuracy, null);
  assert.equal(missingBlack.black.accuracy, null);
  assert.equal(moveAccuracy({ player: 'white', evaluation_before: cp(0) }), null);
  for (const evaluation of [null, {}, { cp: null }, { cp: NaN }, { mate: 0 }]) {
    assert.equal(whiteWinPercent(evaluation), null);
    assert.equal(graphScore(evaluation), null);
  }
});

test('graph caps display scores, preserves mate direction, and honors terminal results', () => {
  assert.equal(graphScore(cp(125)), 1.25);
  assert.equal(graphScore(cp(3000)), 10);
  assert.equal(graphScore(cp(-3000)), -10);
  assert.equal(graphScore({ mate: 3 }), 10);
  assert.equal(graphScore({ mate: -3 }), -10);
  assert.equal(graphScore({ mate: 0, terminal_result: '1-0' }), 10);
  assert.equal(graphScore({ mate: 0, terminal_result: '0-1' }), -10);
  assert.equal(graphScore({ terminal_result: '1/2-1/2' }), 0);
});

test('series includes the initial position and actual evaluations with custom move numbering', () => {
  const moves = [{ ...move('black', 25, -35), fullmove_number: 17, played_move_san: 'e5', best_fen: 'not plotted' }];
  assert.deepEqual(evaluationSeries(moves).map(({ label, score }) => ({ label, score })), [
    { label: 'Start', score: 0.25 }, { label: '17… e5', score: -0.35 },
  ]);
  assert.deepEqual(evaluationSeries([]), []);
});