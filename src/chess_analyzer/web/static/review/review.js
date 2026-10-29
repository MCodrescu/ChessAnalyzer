import { formatGameResult, moveSquares, positionFor } from './review-state.js';
import { ReviewSummary } from './review-summary.js';
import { RatingSummary } from './rating-summary.js';
import { importDialog, setReviewStatus } from './import-dialog.js';
import { selectedGamePGN, selectedGameOrientation, setAnalysisBusy, setBoardReady } from './chesscom-import.js';

const $ = (id) => document.getElementById(id);
let ground;
let analysis;
let selected = 0;
let preview = 'before';
let Chess;
let legalDestinations;
let boardPosition;
let pendingPromotion;
let positionSearchVersion = 0;
let positionSearchTimer;
let positionSearchQueue = Promise.resolve();
const summary = new ReviewSummary(selectMove);
const ratings = new RatingSummary();

function showGameOver(result, variation = false) {
  const outcome = formatGameResult(result);
  $('game-over').textContent = outcome
    ? `${variation ? 'Variation over' : 'Game over'} · ${outcome}`
    : 'End of recorded game · Result unknown';
  $('game-over').hidden = false;
}

function cancelPositionSearch() {
  positionSearchVersion++;
  clearTimeout(positionSearchTimer);
  $('position-search-status').textContent = '';
  $('retry-position').hidden = true;
}

function searchPosition() {
  cancelPositionSearch();
  const version = positionSearchVersion;
  const fen = boardPosition.fen();
  const chess960 = boardPosition.chess960;
  $('position-search-status').textContent = 'Stockfish is searching the shown position.';
  ground.setAutoShapes([]);
  // Serialize searches: abandoning a browser request does not stop its engine.
  positionSearchTimer = setTimeout(() => {
    positionSearchQueue = positionSearchQueue.then(async () => {
      if (version !== positionSearchVersion) return;
      try {
        const response = await fetch(document.body.dataset.positionUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value },
          body: JSON.stringify({ fen, chess960 }),
        });
        if (!(response.headers.get('content-type') || '').includes('application/json')) {
          throw new Error('The server returned an unexpected response. Check the analysis server and CSRF settings.');
        }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Position analysis failed. Please try again.');
        if (version !== positionSearchVersion) return;
        $('position-search-status').textContent = data.evaluation.terminal_result
          ? `Game over: ${formatGameResult(data.evaluation.terminal_result)}.`
          : 'Local Stockfish suggestion for the shown position. Game scores are unchanged.';
        if (data.evaluation.terminal_result) {
          showGameOver(data.evaluation.terminal_result, boardPosition.history().length > 0 || preview === 'best');
        }
        if (data.best_move_uci) {
          const [orig, dest] = moveSquares(data.best_move_uci);
          ground.setAutoShapes([{ orig, dest, brush: 'green' }]);
        }
      } catch (error) {
        if (version !== positionSearchVersion) return;
        $('position-search-status').textContent = error.message || 'Unable to reach the analysis server.';
        $('retry-position').hidden = false;
      }
    });
  }, 150);
}

$('retry-position').addEventListener('click', searchPosition);

function showError(message) {
  for (const id of ['error', 'import-error']) {
    $(id).textContent = message;
    $(id).hidden = !message;
  }
}

// A missing build should produce an actionable message, not a broken page.
try {
  const { Chessground } = await import('./vendor/chessground.js');
  ({ Chess, legalDestinations } = await import('./vendor/board-rules.js'));
  ground = Chessground($('board'), {
    viewOnly: false,
    coordinates: true,
    animation: { enabled: true, duration: 180 },
    autoCastle: false,
    drawable: { enabled: false, visible: true },
    movable: { free: false, rookCastle: false, events: { after: (from, to) => playBoardMove(from, to) } },
    premovable: { enabled: false },
  });
  loadBoardPosition(new Chess().fen());
  setBoardReady(true);
} catch {
  showError('Board assets are missing. Run npm ci and npm run build, then reload.');
  setBoardReady(false);
}

function renderBoardPosition(lastMove, shapes = ground.state.drawable.autoShapes) {
  const color = boardPosition.turn() === 'w' ? 'white' : 'black';
  ground.set({
    fen: boardPosition.fen(), lastMove, check: boardPosition.isCheck() ? color : false,
    turnColor: color, selected: undefined,
    movable: { color, rookCastle: boardPosition.chess960, dests: legalDestinations(boardPosition) },
  });
  ground.setAutoShapes(shapes);
  // Expose the actual full position, rather than Chessground's placement-only FEN.
  $('board').dataset.fen = boardPosition.fen();
  const exploring = boardPosition.history().length > 0;
  const variationMode = exploring;
  document.body.classList.toggle('variation-mode', variationMode);
  $('undo-variation').disabled = !exploring;
  $('reset-variation').disabled = !variationMode;
}

function loadBoardPosition(fen, lastMove, shapes = []) {
  cancelPositionSearch();
  $('game-over').hidden = true;
  pendingPromotion = undefined;
  if ($('promotion-dialog').open) $('promotion-dialog').close();
  boardPosition = new Chess(fen, { chess960: analysis?.chess960 === true });
  renderBoardPosition(lastMove, shapes);
}

function renderVariation(lastMove) {
  $('game-over').hidden = true;
  renderBoardPosition(lastMove, []);
  const color = boardPosition.turn() === 'w' ? 'White' : 'Black';
  const state = boardPosition.isCheckmate() ? `${color} is checkmated.`
    : boardPosition.isStalemate() ? 'Stalemate.'
      : `${color} to move${boardPosition.isCheck() ? ' · Check' : ''}.`;
  $('board').setAttribute('aria-label', `Interactive chessboard, ${state}`);
  searchPosition();
}

function playBoardMove(from, to, promotion) {
  const choices = boardPosition.moves({ verbose: true }).filter((move) => move.from === from && move.to === to);
  if (!choices.length) {
    renderBoardPosition();
    return;
  }
  if (choices.some((move) => move.promotion) && !promotion) {
    // Chessground has already moved the pawn visually. Restore it while choosing.
    renderBoardPosition();
    pendingPromotion = { from, to };
    $('promotion-dialog').showModal();
    return;
  }
  boardPosition.move({ from, to, ...(promotion ? { promotion } : {}) });
  renderVariation([from, to]);
}

function resetVariation() {
  if (analysis) selectMove(selected, preview);
  else {
    loadBoardPosition(new Chess().fen());
    $('board').setAttribute('aria-label', 'Interactive chessboard, starting position');
  }
}

$('undo-variation').addEventListener('click', () => {
  boardPosition.undo();
  const history = boardPosition.history({ verbose: true });
  if (!history.length && analysis) selectMove(selected, preview);
  else if (!history.length) resetVariation();
  else renderVariation([history.at(-1).from, history.at(-1).to]);
});
$('reset-variation').addEventListener('click', resetVariation);
for (const button of document.querySelectorAll('[data-promotion]')) {
  button.addEventListener('click', () => {
    const move = pendingPromotion;
    pendingPromotion = undefined;
    $('promotion-dialog').close();
    if (move) playBoardMove(move.from, move.to, button.dataset.promotion);
  });
}
function cancelPromotion() {
  pendingPromotion = undefined;
  $('promotion-dialog').close();
}
$('cancel-promotion').addEventListener('click', cancelPromotion);
$('promotion-dialog').addEventListener('cancel', cancelPromotion);

function currentGamePosition() {
  return selected + (preview === 'played' ? 1 : 0);
}

function showRecordedPosition(evaluation) {
  const uci = evaluation.best_move_uci;
  $('position-search-status').textContent = evaluation.terminal_result
    ? `Game over: ${formatGameResult(evaluation.terminal_result)}.`
    : 'Recorded Stockfish analysis for this game position.';
  ground.setAutoShapes(uci ? [{ orig: moveSquares(uci)[0], dest: moveSquares(uci)[1], brush: 'green' }] : []);
}

function navigateGamePosition(position) {
  if (!analysis?.moves.length) return;
  const count = analysis.moves.length;
  const target = Math.max(0, Math.min(position, count));
  selectMove(Math.min(target, count - 1), target === count ? 'played' : 'before');
}

function selectMove(index, nextPreview = 'before') {
  if (!ground || !analysis) return;
  preview = nextPreview;
  selected = Math.max(0, Math.min(index, analysis.moves.length - 1));
  const move = analysis.moves[selected];
  summary.select(selected, preview);
  $('first').disabled = $('previous').disabled = !move || currentGamePosition() === 0;
  $('last').disabled = $('next').disabled = !move || currentGamePosition() === analysis.moves.length;
  if (!move) {
    loadBoardPosition(analysis.initial_fen);
    $('board').setAttribute('aria-label', 'Chessboard, game starting position');
    $('move-counter').textContent = 'No moves';
    if (formatGameResult(analysis.headers.Result)) showGameOver(analysis.headers.Result);
    return;
  }
  const position = positionFor(move, preview);
  const finalPosition = preview === 'played' && selected === analysis.moves.length - 1;
  loadBoardPosition(position.fen, position.lastMove, position.shapes);
  $('board').setAttribute('aria-label', `Chessboard, ${finalPosition ? 'final position after' : `${preview} position for`} ${move.fullmove_number}${move.player === 'white' ? '.' : '…'} ${move.played_move_san}`);
  $('move-counter').textContent = `${selected + 1} / ${analysis.moves.length}`;
  if (finalPosition) {
    const result = move.evaluation_after?.terminal_result || analysis.headers.Result;
    showGameOver(result);
  }
  if (preview === 'played' && move.evaluation_after && 'best_move_uci' in move.evaluation_after) {
    showRecordedPosition(move.evaluation_after);
  } else if (preview !== 'before') searchPosition();
}

$('analysis-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const pgn = selectedGamePGN();
  if (!ground || !pgn) return;
  const orientation = selectedGameOrientation();
  cancelPositionSearch();
  showError('');
  setAnalysisBusy(true);
  $('analyze-button').textContent = 'Analyzing…';
  $('analysis-form').setAttribute('aria-busy', 'true');
  setReviewStatus('Stockfish is reviewing the game. Accuracy and performance rating share one analysis. This can take several minutes.');
  try {
    await positionSearchQueue;
    const data = await ratings.loadReview($('analysis-form').action, pgn, setReviewStatus);
    analysis = data;
    for (const color of ['White', 'Black']) {
      const name = data.headers[color] || color;
      const rating = String(data.headers[`${color}Elo`] || '').trim();
      const hasRating = /^\d+$/.test(rating) && Number(rating) > 0;
      $(`${color.toLowerCase()}-player`).textContent = hasRating ? `${name} (${rating})` : name;
    }
    $('game-event').textContent = data.headers.Event || 'Imported game';
    $('game-result').textContent = `Result: ${data.headers.Result || '*'} · ${data.moves.length} half-moves`;
    summary.render(data);
    ratings.render(data);
    setOrientation(orientation);
    selectMove(0);
    setReviewStatus('Analysis complete.');
    importDialog.close();
  } catch (error) {
    showError(error.message || 'Unable to reach the analysis server.');
    setReviewStatus('Analysis did not complete. Your previous review is still available.');
  } finally {
    setAnalysisBusy(false);
    $('analyze-button').textContent = 'Analyze game';
    $('analysis-form').setAttribute('aria-busy', 'false');
  }
});

function setOrientation(orientation) {
  ground.set({ orientation });
  const whiteCard = $('white-player').closest('.player-card');
  const blackCard = $('black-player').closest('.player-card');
  const board = $('board').closest('.board-shell');
  const whiteAtBottom = ground.state.orientation === 'white';
  // Move whole cards so names, color indicators, and metadata stay together.
  board.before(whiteAtBottom ? blackCard : whiteCard);
  board.after(whiteAtBottom ? whiteCard : blackCard);
}

$('flip').addEventListener('click', () => {
  if (!ground) return;
  setOrientation(ground.state.orientation === 'white' ? 'black' : 'white');
});
$('first').addEventListener('click', () => navigateGamePosition(0));
$('previous').addEventListener('click', () => navigateGamePosition(currentGamePosition() - 1));
$('next').addEventListener('click', () => navigateGamePosition(currentGamePosition() + 1));
$('last').addEventListener('click', () => navigateGamePosition(analysis.moves.length));
document.addEventListener('keydown', (event) => {
  if (importDialog.open || $('promotion-dialog').open) return;
  if (!analysis?.moves.length || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  if (event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
  const position = currentGamePosition();
  const targets = { ArrowLeft: position - 1, ArrowRight: position + 1, Home: 0, End: analysis.moves.length };
  if (event.key in targets) {
    event.preventDefault();
    navigateGamePosition(targets[event.key]);
  }
});