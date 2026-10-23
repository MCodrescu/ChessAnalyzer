import assert from 'node:assert/strict';
import test from 'node:test';
import { formatEvaluation, formatGameResult, moveSquares, positionFor } from '../../src/chess_analyzer/web/static/review/review-state.js';

const move = {
  fen_before: 'before', fen_after: 'after', best_fen: 'best',
  played_move_uci: 'e2e4', best_move_uci: 'd2d4', is_best_move: false,
};

test('score formatting preserves White-relative CP, signed mate, and results', () => {
  assert.equal(formatEvaluation({ cp: 125, mate: null }), '+1.25');
  assert.equal(formatEvaluation({ cp: -35, mate: null }), '-0.35');
  assert.equal(formatEvaluation({ cp: 0, mate: null }), '+0.00');
  assert.equal(formatEvaluation({ cp: null, mate: -3 }), 'M-3');
  assert.equal(formatEvaluation({ cp: null, mate: 2 }), 'M+2');
  assert.equal(formatEvaluation({ mate: 0, terminal_result: '0-1' }), '0-1');
  assert.equal(formatEvaluation(null), '—');
});

test('game results name the winner or draw without inferring an unfinished result', () => {
  assert.equal(formatGameResult('1-0'), 'White wins (1-0)');
  assert.equal(formatGameResult('0-1'), 'Black wins (0-1)');
  assert.equal(formatGameResult('1/2-1/2'), 'Draw (1/2-1/2)');
  for (const result of ['*', '', undefined, null, 'invalid']) {
    assert.equal(formatGameResult(result), null);
  }
});

test('comparison arrows share the before-move position', () => {
  const position = positionFor(move, 'before');
  assert.equal(position.fen, 'before');
  assert.equal(position.lastMove, undefined);
  assert.deepEqual(position.shapes, [
    { orig: 'd2', dest: 'd4', brush: 'green' },
    { orig: 'e2', dest: 'e4', brush: 'blue' },
  ]);
  assert.equal(positionFor({ ...move, is_best_move: true }, 'before').shapes.length, 1);
});

test('played and best previews select distinct positions and last moves', () => {
  assert.deepEqual(positionFor(move, 'played'), { fen: 'after', lastMove: ['e2', 'e4'], shapes: [] });
  assert.deepEqual(positionFor(move, 'best'), { fen: 'best', lastMove: ['d2', 'd4'], shapes: [] });
});

test('promotion UCI still produces valid arrow squares', () => {
  assert.deepEqual(moveSquares('a7a8q'), ['a7', 'a8']);
});