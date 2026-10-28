import assert from 'node:assert/strict';
import test from 'node:test';
import { formatEvaluation, formatGameResult, moveSquares, positionFor } from '../../src/chess_analyzer/web/static/review/review-state.js';
import { RatingSummary } from '../../src/chess_analyzer/web/static/review/rating-summary.js';

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

function ratingDOM(context) {
  const elements = new Map();
  const original = globalThis.document;
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      textContent: '', hidden: false, value: 'csrf',
      addEventListener(name, callback) { this[name] = callback; },
      removeAttribute(name) { delete this[name]; },
    });
    return elements.get(id);
  };
  globalThis.document = {
    body: { dataset: { ratingUrl: '/api/ratings/' } },
    getElementById: element,
    querySelector: () => element('csrf'),
  };
  context.after(() => {
    if (original === undefined) delete globalThis.document;
    else globalThis.document = original;
  });
  return element;
}

test('rating results from an old game cannot overwrite the current game', async (context) => {
  const element = ratingDOM(context);
  const responses = [];
  context.mock.method(globalThis, 'fetch', () => new Promise((resolve) => responses.push(resolve)));
  const ratings = new RatingSummary();
  const old = ratings.loadReview('/api/analyze/', 'old game');
  const rejected = assert.rejects(old, { name: 'AbortError' });
  const current = ratings.loadReview('/api/analyze/', 'new game');
  const complete = (white) => ({ ok: true, json: async () => ({
    status: 'complete', review: { moves: [] }, result: { white, black: 1200, model_id: 'model' },
  }) });
  responses[1](complete(1500));
  ratings.render(await current);
  responses[0](complete(900));
  await rejected;
  assert.equal(element('white-rating').textContent, '1500');
});

test('analysis failures propagate without submitting a second rating job', async (context) => {
  const element = ratingDOM(context);
  let status = 400;
  context.mock.method(globalThis, 'fetch', async () => ({
    ok: false, status, json: async () => ({ error: 'Unavailable' }),
  }));
  const ratings = new RatingSummary();
  await assert.rejects(ratings.loadReview('/api/analyze/', 'game'), /Unavailable/);
  status = 429;
  await assert.rejects(ratings.loadReview('/api/analyze/', 'game'), /Unavailable/);
  ratings.render({ moves: [], rating_error: 'Unsupported time control.' });
  assert.equal(element('retry-rating').hidden, true);
  assert.equal(element('rating-status').textContent, 'Unsupported time control.');
});

test('rating HTML errors report the HTTP status instead of a generic retrieval failure', async (context) => {
  const element = ratingDOM(context);
  let status = 500;
  context.mock.method(globalThis, 'fetch', async () => new Response('<html>Private server error</html>', {
    status, headers: { 'Content-Type': 'text/html' },
  }));
  const ratings = new RatingSummary();
  await assert.rejects(ratings.loadReview('/api/analyze/', 'game'), /HTTP 500/);
  assert.doesNotMatch(element('rating-status').textContent, /Private server error/);
  status = 403;
  await assert.rejects(ratings.loadReview('/api/analyze/', 'game'), /HTTP 403.*reload/i);
});