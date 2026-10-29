/** Select a public completed game for one-click analysis, without manual PGN input. */
import { setReviewStatus } from './import-dialog.js';

const $ = (id) => document.getElementById(id);
const form = $('chesscom-form');
let username = '';
let games = [];
let currentPage = 1;
let pages = 1;
let requestId = 0;
let controller;
let selectedPgn = '';
let selectedOrientation = 'white';
let lookupBusy = false;
let analysisBusy = false;
let boardReady = false;

/** Read the current selection only when it is safe to start a new analysis. */
export function selectedGamePGN() {
  return boardReady && !lookupBusy && !analysisBusy ? selectedPgn : '';
}

/** Board perspective belonging to the selected archive game's searched player. */
export function selectedGameOrientation() {
  return selectedOrientation;
}

/** Keep selection controls locked for the entire in-flight analysis. */
export function setAnalysisBusy(busy) {
  analysisBusy = busy;
  updateControls();
}

/** Prevent submission if the board assets have not loaded successfully. */
export function setBoardReady(ready) {
  boardReady = ready;
  updateControls();
}

function selectGame(pgn = '', orientation = 'white') {
  selectedPgn = pgn;
  selectedOrientation = orientation;
  if (boardReady) {
    $('error').hidden = true;
    $('import-error').hidden = true;
  }
  updateControls();
}

function selectListedGame() {
  const index = $('chesscom-game').selectedIndex;
  const game = games[index];
  const orientation = game?.black.username.toLowerCase() === username.toLowerCase() ? 'black' : 'white';
  selectGame(game?.pgn || '', orientation);
}

function showError(message = '') {
  $('chesscom-error').textContent = message;
  $('chesscom-error').hidden = !message;
}

function updateControls() {
  const busy = lookupBusy || analysisBusy;
  form.setAttribute('aria-busy', String(lookupBusy));
  $('chesscom-username').disabled = analysisBusy;
  $('chesscom-search').disabled = busy;
  $('chesscom-search').textContent = lookupBusy ? 'Loading…' : 'Find games';
  $('chesscom-month').disabled = busy;
  $('chesscom-game').disabled = busy || !games.length;
  $('games-previous').disabled = busy || !games.length || currentPage <= 1;
  $('games-next').disabled = busy || !games.length || currentPage >= pages;
  $('demo').disabled = analysisBusy;
  $('analyze-button').disabled = busy || !boardReady || !selectedPgn;
}

async function request(params, signal) {
  const url = new URL(form.action);
  url.search = new URLSearchParams(params).toString();
  const response = await fetch(url, { credentials: 'same-origin', signal });
  if (!(response.headers.get('content-type') || '').includes('application/json')) {
    throw new Error('The game lookup returned an unexpected response. Please try again.');
  }
  const data = await response.json();
  signal.throwIfAborted();
  if (!response.ok) throw new Error(data.error || 'Unable to fetch Chess.com games.');
  return data;
}

async function runLookup(action) {
  if (analysisBusy) return;
  controller?.abort();
  controller = new AbortController();
  const id = ++requestId;
  showError();
  lookupBusy = true;
  selectGame();
  $('chesscom-status').textContent = 'Fetching public games from Chess.com…';
  try {
    await action(controller.signal);
  } catch (error) {
    if (id !== requestId || error.name === 'AbortError') return;
    showError(error.message || 'Unable to reach the game lookup server.');
    $('chesscom-status').textContent = 'Lookup did not complete. Try again or use the example game.';
  } finally {
    if (id === requestId) {
      lookupBusy = false;
      updateControls();
    }
  }
}

function playerLabel(player) {
  return `${player.username}${player.rating === null ? '' : ` (${player.rating})`}`;
}

function resultLabel(game) {
  if (game.white.result === 'win') return '1–0';
  if (game.black.result === 'win') return '0–1';
  const draws = ['agreed', 'repetition', 'stalemate', 'insufficient', '50move', 'timevsinsufficient'];
  if (draws.includes(game.white.result) || draws.includes(game.black.result)) return '½–½';
  return `${game.white.result} / ${game.black.result}`;
}

async function loadMonth(page, signal) {
  // Clear old options before a new request so errors cannot leave a game from
  // another month/page selectable under the new archive label.
  games = [];
  $('chesscom-game').replaceChildren();
  $('games-page').textContent = '';
  const [year, month] = $('chesscom-month').value.split('-');
  const data = await request({ username, year, month, page }, signal);
  games = data.games;
  currentPage = data.page;
  pages = data.pages;
  for (const [index, game] of games.entries()) {
    const date = new Date(game.end_time * 1000).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
    const variant = game.rules === 'chess960' ? ' · Chess960' : '';
    const label = `${date} · ${playerLabel(game.white)} vs ${playerLabel(game.black)}${variant} · ${game.time_class} ${game.time_control} · ${resultLabel(game)}`;
    $('chesscom-game').add(new Option(label, String(index)));
  }
  if (games.length) $('chesscom-game').selectedIndex = 0;
  selectListedGame();
  $('games-page').textContent = `${data.total} games · ${currentPage} / ${pages}`;
  $('chesscom-status').textContent = games.length
    ? ''
    : 'No completed standard or Chess960 games with importable PGNs in this month. Try another archive month.';
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (analysisBusy) return;
  $('chesscom-picker').hidden = true;
  games = [];
  runLookup(async (signal) => {
    const data = await request({ username: $('chesscom-username').value.trim() }, signal);
    username = data.username;
    $('chesscom-month').replaceChildren();
    for (const archive of data.archives) {
      $('chesscom-month').add(new Option(archive.label, archive.label));
    }
    if (!data.archives.length) {
      $('chesscom-status').textContent = `No completed-game archives found for ${username}.`;
      return;
    }
    $('chesscom-picker').hidden = false;
    await loadMonth(1, signal);
  });
});

$('chesscom-username').addEventListener('input', () => {
  if (analysisBusy) return;
  ++requestId;
  controller?.abort();
  username = '';
  games = [];
  $('chesscom-picker').hidden = true;
  showError();
  lookupBusy = false;
  selectGame();
  $('chesscom-status').textContent = 'Public completed games only. No login needed.';
});
$('chesscom-month').addEventListener('change', () => runLookup((signal) => loadMonth(1, signal)));
$('games-previous').addEventListener('click', () => runLookup((signal) => loadMonth(currentPage - 1, signal)));
$('games-next').addEventListener('click', () => runLookup((signal) => loadMonth(currentPage + 1, signal)));
$('chesscom-game').addEventListener('change', () => {
  if (!lookupBusy && !analysisBusy) selectListedGame();
});
$('demo').addEventListener('click', () => {
  if (analysisBusy) return;
  ++requestId;
  controller?.abort();
  lookupBusy = false;
  games = [];
  $('chesscom-game').replaceChildren();
  $('chesscom-picker').hidden = true;
  showError();
  selectGame('[Event "A quick lesson"]\n[White "Curious player"]\n[Black "Club opponent"]\n[Result "0-1"]\n\n1. f3 e5 2. g4 Qh4# 0-1');
  $('chesscom-status').textContent = 'Example selected. No Chess.com lookup needed.';
  setReviewStatus('Example selected: Fool’s mate. Select Analyze game to explore.');
});
