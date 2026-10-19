import { Chess as Position, castlingSide } from 'chessops/chess';
import { INITIAL_FEN, makeFen, parseFen } from 'chessops/fen';
import { makeSan } from 'chessops/san';
import { charToRole, kingCastlesTo, makeSquare, parseSquare, roleToChar } from 'chessops/util';

/** Interactive rules shared by standard and Chess960 boards. */
export class Chess {
  constructor(fen = INITIAL_FEN, { chess960 = false } = {}) {
    this.chess960 = chess960;
    this.load(fen);
  }

  load(fen) {
    this.position = Position.fromSetup(parseFen(fen).unwrap()).unwrap();
    this.stack = [];
  }

  fen() { return makeFen(this.position.toSetup()); }
  turn() { return this.position.turn[0]; }
  isCheck() { return this.position.isCheck(); }
  isCheckmate() { return this.position.isCheckmate(); }
  isStalemate() { return this.position.isStalemate(); }

  get(square) {
    const piece = this.position.board.get(parseSquare(square));
    return piece ? { type: roleToChar(piece.role), color: piece.color[0] } : undefined;
  }

  moves({ verbose = false } = {}) {
    const result = [];
    for (const [from, destinations] of this.position.allDests()) {
      for (const to of destinations) {
        const promotions = this.position.board.pawn.has(from) && (to < 8 || to >= 56)
          ? ['queen', 'rook', 'bishop', 'knight'] : [undefined];
        for (const promotion of promotions) {
          const raw = { from, to, ...(promotion ? { promotion } : {}) };
          const side = castlingSide(this.position, raw);
          const destination = side && !this.chess960 ? kingCastlesTo(this.position.turn, side) : to;
          const move = {
            from: makeSquare(from), to: makeSquare(destination),
            ...(promotion ? { promotion: roleToChar(promotion) } : {}),
            san: makeSan(this.position, raw),
          };
          result.push(verbose ? move : move.san);
        }
      }
    }
    return result;
  }

  move(input) {
    const move = this.moves({ verbose: true }).find((candidate) => typeof input === 'string'
      ? candidate.san === input
      : candidate.from === input.from && candidate.to === input.to && candidate.promotion === input.promotion);
    if (!move) throw new Error('Illegal move for the current position.');
    const raw = {
      from: parseSquare(move.from), to: parseSquare(move.to),
      ...(move.promotion ? { promotion: charToRole(move.promotion) } : {}),
    };
    this.stack.push({ position: this.position.clone(), move });
    this.position.play(raw);
    return move;
  }

  history({ verbose = false } = {}) {
    return this.stack.map(({ move }) => verbose ? move : move.san);
  }

  undo() {
    const entry = this.stack.pop();
    if (!entry) throw new Error('No trial move to undo.');
    this.position = entry.position;
    return entry.move;
  }
}

/** Legal Chessground destinations, including all promotion destinations once. */
export function legalDestinations(position) {
  const destinations = new Map();
  for (const { from, to } of position.moves({ verbose: true })) {
    if (!destinations.has(from)) destinations.set(from, []);
    if (!destinations.get(from).includes(to)) destinations.get(from).push(to);
  }
  return destinations;
}