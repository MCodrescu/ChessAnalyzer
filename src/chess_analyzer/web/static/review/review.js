import { formatEvaluation, positionFor } from './review-state.js';
import { ReviewSummary } from './review-summary.js';
import { importDialog, setReviewStatus } from './import-dialog.js';
import { selectedGamePGN, selectedGameOrientation, setAnalysisBusy, setBoardReady } from './chesscom-import.js';

const $ = (id) => document.getElementById(id);
let ground;
let analysis;
let selected = 0;
let preview = 'before';
let moveButtons = [];
let Chess;
let legalDestinations;
let boardPosition;
let pendingPromotion;
const summary = new ReviewSummary(selectMove);

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

function renderBoardPosition(lastMove, shapes = []) {
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
  $('undo-variation').disabled = $('reset-variation').disabled = !exploring;
}

function loadBoardPosition(fen, lastMove, shapes) {
  pendingPromotion = undefined;
  if ($('promotion-dialog').open) $('promotion-dialog').close();
  boardPosition = new Chess(fen, { chess960: analysis?.chess960 === true });
  renderBoardPosition(lastMove, shapes);
}

function renderVariation(lastMove) {
  renderBoardPosition(lastMove);
  const color = boardPosition.turn() === 'w' ? 'White' : 'Black';
  const state = boardPosition.isCheckmate() ? `${color} is checkmated.`
    : boardPosition.isStalemate() ? 'Stalemate.'
      : `${color} to move${boardPosition.isCheck() ? ' · Check' : ''}.`;
  const line = boardPosition.history().join(' ');
  $('board').setAttribute('aria-label', `Interactive chessboard, ${state}`);
  $('quality').textContent = 'EXPLORING';
  $('position-label').textContent = `Your variation: ${line}`;
  $('evaluation').textContent = 'Not searched';
  $('cp-loss').textContent = '—';
  $('played-move').textContent = $('best-move').textContent = '—';
  for (const button of document.querySelectorAll('[data-preview]')) button.setAttribute('aria-pressed', 'false');
  $('preview-note').textContent = `${state} Click or drag pieces to try legal moves. Undo or Reset to return. Original game scores and graph are unchanged; this variation is not analyzed.`;
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
    $('quality').textContent = 'READY TO EXPLORE';
    $('position-label').textContent = 'Select a move after analyzing a game.';
    $('preview-note').textContent = 'Click or drag pieces to try legal moves, or load a game to review.';
  }
}

$('undo-variation').addEventListener('click', () => {
  boardPosition.undo();
  const history = boardPosition.history({ verbose: true });
  if (!history.length) resetVariation();
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

function renderMoveList() {
  const list = $('move-list');
  list.replaceChildren();
  moveButtons = [];
  for (const [index, move] of analysis.moves.entries()) {
    const button = document.createElement('button');
    button.className = `move-button${move.is_best_move ? ' engine-match' : ''}`;
    const prefix = `${move.fullmove_number}${move.player === 'white' ? '.' : '…'}`;
    button.textContent = `${prefix} ${move.played_move_san}`;
    button.setAttribute('aria-label', `${prefix} ${move.played_move_san}, ${move.player}`);
    button.addEventListener('click', () => selectMove(index));
    moveButtons.push(button);
    list.append(button);
  }
  if (!analysis.moves.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'This game has no moves. Showing its starting position.';
    list.append(empty);
  }
}

function selectMove(index, nextPreview = 'before') {
  if (!ground || !analysis) return;
  preview = nextPreview;
  selected = Math.max(0, Math.min(index, analysis.moves.length - 1));
  const move = analysis.moves[selected];
  summary.select(selected, preview);
  for (const [i, button] of moveButtons.entries()) {
    button.setAttribute('aria-current', String(i === selected));
  }
  for (const button of document.querySelectorAll('[data-preview]')) {
    button.disabled = !move;
    button.setAttribute('aria-pressed', String(button.dataset.preview === preview));
  }
  $('first').disabled = $('previous').disabled = !move || selected === 0;
  $('last').disabled = $('next').disabled = !move || selected === analysis.moves.length - 1;
  if (!move) {
    loadBoardPosition(analysis.initial_fen);
    $('board').setAttribute('aria-label', 'Chessboard, game starting position');
    $('move-counter').textContent = 'No moves';
    $('position-label').textContent = 'Game starting position';
    $('quality').textContent = 'NO MOVES';
    for (const id of ['played-move', 'best-move', 'evaluation', 'cp-loss']) $(id).textContent = '—';
    $('preview-note').textContent = 'This game has no moves to compare.';
    return;
  }
  const position = positionFor(move, preview);
  loadBoardPosition(position.fen, position.lastMove, position.shapes);
  $('board').setAttribute('aria-label', `Chessboard, ${preview} position for ${move.fullmove_number}${move.player === 'white' ? '.' : '…'} ${move.played_move_san}`);
  $('move-counter').textContent = `${selected + 1} / ${analysis.moves.length}`;
  $('position-label').textContent = `${move.fullmove_number}${move.player === 'white' ? '.' : '…'} ${move.played_move_san} · ${move.player} to play before this move`;
  $('played-move').textContent = move.played_move_san;
  $('best-move').textContent = move.best_move_san;
  $('quality').textContent = move.is_best_move ? 'ENGINE MATCH' : 'COMPARE MOVES';
  $('cp-loss').textContent = move.estimated_cp_loss === null ? 'Mate transition' : `${move.estimated_cp_loss} cp`;
  // A best-line preview is not searched separately; never display the played
  // position's evaluation as if it belonged to the engine's alternative.
  $('evaluation').textContent = preview === 'best' ? 'Not searched' : formatEvaluation(preview === 'played' ? move.evaluation_after : move.evaluation_before);
  $('preview-note').textContent = preview === 'before'
    ? 'Before the move: green = engine best, blue = played. One arrow if they match.'
    : preview === 'played' ? 'Position after the actual game move.' : 'Position after the engine’s suggested move (one-move preview).';
  // Reveal the selection inside the move list without scrolling the page/board.
  const list = $('move-list');
  const buttonBounds = moveButtons[selected].getBoundingClientRect();
  const listTop = list.getBoundingClientRect().top + list.clientTop;
  const listBottom = listTop + list.clientHeight;
  if (buttonBounds.top < listTop) {
    list.scrollTop += buttonBounds.top - listTop;
  } else if (buttonBounds.bottom > listBottom) {
    list.scrollTop += buttonBounds.bottom - listBottom;
  }
}

$('analysis-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const pgn = selectedGamePGN();
  if (!ground || !pgn) return;
  const orientation = selectedGameOrientation();
  showError('');
  setAnalysisBusy(true);
  $('analyze-button').textContent = 'Analyzing…';
  $('analysis-form').setAttribute('aria-busy', 'true');
  setReviewStatus('Stockfish is reviewing every position. A typical game takes 10–30 seconds; longer games can take several minutes. Keep this tab open.');
  try {
    const response = await fetch(event.currentTarget.action, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value },
      body: JSON.stringify({ pgn }),
    });
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) throw new Error('The server returned an unexpected response. Check CSRF settings, request limits, and server timeouts.');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Analysis failed. Please try again.');
    analysis = data;
    $('white-player').textContent = data.headers.White || 'White';
    $('black-player').textContent = data.headers.Black || 'Black';
    $('game-event').textContent = data.headers.Event || 'Imported game';
    $('game-result').textContent = `Result: ${data.headers.Result || '*'} · ${data.moves.length} half-moves`;
    $('analysis-settings').textContent = `DEPTH ≤ ${data.analysis_depth} · ${data.analysis_time_seconds === null ? 'DEPTH ONLY' : `${data.analysis_time_seconds}s/POS`}`;
    renderMoveList();
    summary.render(data);
    setOrientation(orientation);
    selectMove(0);
    setReviewStatus('Analysis complete. Click any move to compare the choices.');
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
$('first').addEventListener('click', () => selectMove(0));
$('previous').addEventListener('click', () => selectMove(selected - 1));
$('next').addEventListener('click', () => selectMove(selected + 1));
$('last').addEventListener('click', () => selectMove(analysis.moves.length - 1));
for (const button of document.querySelectorAll('[data-preview]')) {
  button.addEventListener('click', () => selectMove(selected, button.dataset.preview));
}
document.addEventListener('keydown', (event) => {
  if (importDialog.open || $('promotion-dialog').open) return;
  if (!analysis?.moves.length || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  if (event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
  const targets = { ArrowLeft: selected - 1, ArrowRight: selected + 1, Home: 0, End: analysis.moves.length - 1 };
  if (event.key in targets) {
    event.preventDefault();
    selectMove(targets[event.key]);
  }
});