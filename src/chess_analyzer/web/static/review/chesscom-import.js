/** Import a public completed game, without starting analysis automatically. */
import { setReviewStatus } from './import-dialog.js';

const $ = (id) => document.getElementById(id);
const form = $('chesscom-form');
let username = '';
let games = [];
let currentPage = 1;
let pages = 1;
let requestId = 0;
let controller;

function showError(message = '') {
  $('chesscom-error').textContent = message;
  $('chesscom-error').hidden = !message;
}

function setBusy(busy) {
  form.setAttribute('aria-busy', String(busy));
  $('chesscom-search').disabled = busy;
  $('chesscom-search').textContent = busy ? 'Loading…' : 'Find games';
  $('chesscom-month').disabled = busy;
  $('chesscom-game').disabled = busy || !games.length;
  $('chesscom-load').disabled = busy || !games.length;
  $('games-previous').disabled = busy || !games.length || currentPage <= 1;
  $('games-next').disabled = busy || !games.length || currentPage >= pages;
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
  controller?.abort();
  controller = new AbortController();
  const id = ++requestId;
  showError();
  setBusy(true);
  $('chesscom-status').textContent = 'Fetching public games from Chess.com…';
  try {
    await action(controller.signal);
  } catch (error) {
    if (id !== requestId || error.name === 'AbortError') return;
    showError(error.message || 'Unable to reach the game lookup server.');
    $('chesscom-status').textContent = 'Lookup did not complete. Try again or import a PGN below.';
  } finally {
    if (id === requestId) setBusy(false);
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
    const label = `${date} · ${playerLabel(game.white)} vs ${playerLabel(game.black)} · ${game.time_class} ${game.time_control} · ${resultLabel(game)}`;
    $('chesscom-game').add(new Option(label, String(index)));
  }
  if (games.length) $('chesscom-game').selectedIndex = 0;
  $('games-page').textContent = `${data.total} games · ${currentPage} / ${pages}`;
  $('chesscom-status').textContent = games.length
    ? `Choose a game for ${username}, then load it for analysis. Dates use your local time.`
    : 'No completed standard games with importable PGNs in this month. Try another archive month.';
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
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
  ++requestId;
  controller?.abort();
  username = '';
  games = [];
  $('chesscom-picker').hidden = true;
  showError();
  setBusy(false);
  $('chesscom-status').textContent = 'Public completed games only. No login needed.';
});
$('chesscom-month').addEventListener('change', () => runLookup((signal) => loadMonth(1, signal)));
$('games-previous').addEventListener('click', () => runLookup((signal) => loadMonth(currentPage - 1, signal)));
$('games-next').addEventListener('click', () => runLookup((signal) => loadMonth(currentPage + 1, signal)));
$('chesscom-load').addEventListener('click', () => {
  const index = $('chesscom-game').selectedIndex;
  if (index < 0 || !games[index]) return;
  $('pgn').value = games[index].pgn;
  $('error').hidden = true;
  $('import-error').hidden = true;
  setReviewStatus(`Game loaded from Chess.com (${username}). Select Analyze game to begin; any previous review remains until analysis completes.`);
  $('pgn').focus();
});
