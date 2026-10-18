import assert from 'node:assert/strict';
import test from 'node:test';
import { evaluationSeries, gameAccuracy, graphScore, moveAccuracy, whiteWinPercent } from '../../src/chess_analyzer/web/static/review/summary-state.js';

const cp = (value) => ({ cp: value, mate: null, terminal_result: null });
const move = (player, before, after) => ({ player, evaluation_before: cp(before), evaluation_after: cp(after) });

test('winning chances are white-relative, symmetric, and bounded', () => {
  assert.equal(whiteWinPercent(cp(0)), 50);
  assert.ok(Math.abs(whiteWinPercent(cp(100)) - 59.102666) < 0.0001);
  assert.ok(Math.abs(whiteWinPercent(cp(-100)) + whiteWinPercent(cp(100)) - 100) < 1e-10);
  assert.equal(whiteWinPercent(cp(1e9)), 100);
  assert.equal(whiteWinPercent(cp(-1e9)), 0);
});

test('accuracy accounts for mover color and treats improvements as no loss', () => {
  assert.equal(moveAccuracy(move('white', 0, 100)), 100);
  assert.equal(moveAccuracy(move('black', 0, -100)), 100);
  const whiteLoss = moveAccuracy(move('white', 0, -100));
  assert.ok(whiteLoss > 60 && whiteLoss < 70);
  assert.equal(whiteLoss, moveAccuracy(move('black', 0, 100)));
  assert.equal(moveAccuracy({ ...move('white', 0, -10), is_best_move: true }), 100);
});

test('forced mates, checkmate, and draws are scored without inventing CP values', () => {
  assert.equal(whiteWinPercent({ cp: null, mate: 3 }), 100);
  assert.equal(whiteWinPercent({ cp: null, mate: -2 }), 0);
  assert.equal(whiteWinPercent({ mate: 0, terminal_result: '0-1' }), 0);
  assert.equal(whiteWinPercent({ terminal_result: '1-0' }), 100);
  assert.equal(whiteWinPercent({ terminal_result: '1/2-1/2' }), 50);
  assert.equal(moveAccuracy({ player: 'white', evaluation_before: { mate: 2 }, evaluation_after: { mate: -2 } }), 0);
  assert.equal(moveAccuracy({ player: 'black', evaluation_before: { mate: -2 }, evaluation_after: { terminal_result: '0-1' } }), 100);
});

test('overall accuracy averages scored moves separately for each player', () => {
  const losing = move('white', 0, -100);
  const scores = gameAccuracy([move('white', 0, 0), losing, move('black', 0, -100)]);
  assert.equal(scores.white.accuracy, (100 + moveAccuracy(losing)) / 2);
  assert.equal(scores.white.count, 2);
  assert.deepEqual(scores.black, { accuracy: 100, count: 1 });
});

test('empty games, one-sided games, and missing evaluations do not fake accuracy', () => {
  assert.deepEqual(gameAccuracy([]), { white: { accuracy: null, count: 0 }, black: { accuracy: null, count: 0 } });
  assert.equal(gameAccuracy([move('black', 0, 0)]).white.accuracy, null);
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