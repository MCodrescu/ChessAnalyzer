import test from 'node:test';
import assert from 'node:assert/strict';
import { Chess, legalDestinations } from '../../src/chess_analyzer/web/static/review/board-rules.js';

test('destinations allow only legal moves for the side to move', () => {
  const position = new Chess();
  const destinations = legalDestinations(position);
  assert.deepEqual(destinations.get('e2'), ['e3', 'e4']);
  assert.equal(destinations.has('e7'), false);
  assert.equal(destinations.has('e1'), false);
  position.move('e4');
  assert.equal(legalDestinations(position).has('e2'), false);
  assert.deepEqual(legalDestinations(position).get('e7'), ['e5', 'e6']);
});

test('pinned pieces cannot expose their king and mate has no destinations', () => {
  const position = new Chess('4r1k1/8/8/8/8/8/4R3/4K3 w - - 0 1');
  assert.equal(legalDestinations(position).get('e2').includes('d2'), false);
  position.load('rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3');
  assert.equal(legalDestinations(position).size, 0);
});

test('castling and en passant destinations preserve special-move rules', () => {
  const position = new Chess('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1');
  assert.ok(legalDestinations(position).get('e1').includes('g1'));
  assert.ok(legalDestinations(position).get('e1').includes('c1'));
  position.move({ from: 'e1', to: 'g1' });
  assert.equal(position.get('f1').type, 'r');
  assert.equal(position.get('h1'), undefined);
  position.load('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2');
  assert.ok(legalDestinations(position).get('e5').includes('d6'));
  position.move({ from: 'e5', to: 'd6' });
  assert.equal(position.get('d5'), undefined);
});

test('promotion destinations are unique and allow underpromotion', () => {
  const position = new Chess('7k/P7/8/8/8/8/8/7K w - - 0 1');
  assert.deepEqual(legalDestinations(position).get('a7'), ['a8']);
  position.move({ from: 'a7', to: 'a8', promotion: 'n' });
  assert.equal(position.get('a8').type, 'n');
  position.undo();
  assert.equal(position.get('a7').type, 'p');
});

for (const [label, fen, from, to, san, after] of [
  ['stationary rook', '4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1', 'c1', 'f1', 'O-O', '4k3/8/8/8/8/8/8/R4RK1 b - - 1 1'],
  ['stationary king', '4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1', 'c1', 'a1', 'O-O-O', '4k3/8/8/8/8/8/8/2KR1R2 b - - 1 1'],
  ['king and rook swap', '4k3/8/8/8/8/8/8/5KR1 w K - 0 1', 'f1', 'g1', 'O-O', '4k3/8/8/8/8/8/8/5RK1 b - - 1 1'],
  ['black queenside', 'r1k2r2/8/8/8/8/8/8/4K3 b kq - 0 1', 'c8', 'a8', 'O-O-O', '2kr1r2/8/8/8/8/8/8/4K3 w - - 1 2'],
  ['black kingside', 'r1k2r2/8/8/8/8/8/8/4K3 b kq - 0 1', 'c8', 'f8', 'O-O', 'r4rk1/8/8/8/8/8/8/4K3 w - - 1 2'],
]) {
  test(`Chess960 castling: ${label}`, () => {
    const position = new Chess(fen, { chess960: true });
    assert.ok(legalDestinations(position).get(from).includes(to));
    position.move({ from, to });
    assert.equal(position.fen(), after);
    assert.deepEqual(position.history(), [san]);
    position.undo();
    assert.equal(position.fen(), fen);
    assert.deepEqual(position.history(), []);
  });
}

test('Chess960 castling cannot pass through check or expose a stationary king', () => {
  const throughCheck = new Chess('4kr2/8/8/8/8/8/8/2K4R w K - 0 1', { chess960: true });
  assert.equal(legalDestinations(throughCheck).get('c1').includes('h1'), false);
  const exposedKing = new Chess('4k3/8/8/8/8/8/8/rRK5 w Q - 0 1', { chess960: true });
  assert.equal(legalDestinations(exposedKing).get('c1').includes('b1'), false);
  assert.throws(() => exposedKing.move({ from: 'c1', to: 'b1' }), /Illegal move/);
});

test('Chess960 castling is distinct from a one-square king move', () => {
  const position = new Chess('4k3/8/8/8/8/8/8/5K1R w K - 0 1', { chess960: true });
  const moves = position.moves({ verbose: true }).filter(({ from }) => from === 'f1');
  assert.ok(moves.some(({ to, san }) => to === 'g1' && san === 'Kg1'));
  assert.ok(moves.some(({ to, san }) => to === 'h1' && san === 'O-O'));
  position.move({ from: 'f1', to: 'g1' });
  assert.equal(position.get('h1').type, 'r');
  assert.equal(position.get('f1'), undefined);
});