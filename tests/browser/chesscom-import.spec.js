import { test, expect } from '@playwright/test';

const endpoint = /\/api\/chesscom\/games\/(?:\?|$)/;
const pgns = ['[White "Player"]\n\n1. e4 *', '[White "Player"]\n\n1. d4 *'];
const games = pgns.map((pgn, index) => ({
  pgn,
  end_time: 1_792_300_000 - index,
  white: { username: 'Player', rating: 1400, result: index ? 'agreed' : 'win' },
  black: { username: 'Opponent', rating: 1450, result: index ? 'agreed' : 'resigned' },
  time_class: 'blitz', time_control: '180+2',
}));
const archives = {
  username: 'player',
  archives: [
    { year: 2026, month: 10, label: '2026-10' },
    { year: 2026, month: 9, label: '2026-09' },
  ],
};

async function openLoader(page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
}

test('finds a username, selects a game and sends its PGN for analysis', async ({ page }) => {
  const calls = [];
  await page.route(endpoint, (route) => {
    const params = new URL(route.request().url()).searchParams;
    calls.push(Object.fromEntries(params));
    return route.fulfill({ json: params.has('month')
      ? { username: 'player', page: 1, pages: 1, total: 2, games }
      : archives });
  });
  let analysisPGN;
  await page.route('**/api/analyze/', (route) => {
    analysisPGN = route.request().postDataJSON().pgn;
    return route.fulfill({ json: {
      headers: { White: 'Player', Black: 'Opponent' }, moves: [],
      initial_fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      analysis_depth: 12, analysis_time_seconds: 0.2,
    } });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-game option')).toHaveCount(2);
  await expect(page.locator('#chesscom-game option').first()).toContainText('Player (1400) vs Opponent (1450)');
  await expect(page.locator('#chesscom-game option').first()).toContainText('1–0');
  await expect(page.locator('#chesscom-game option').last()).toContainText('½–½');
  await page.locator('#chesscom-game').selectOption('1');
  await expect(page.locator('#chesscom-game option:checked')).toContainText('½–½');
  await expect(page.locator('#selected-game')).toHaveCount(0);
  await expect(page.locator('#chesscom-status')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Load selected game' })).toHaveCount(0);
  await expect(page.locator('textarea, input[type="file"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Analyze game' })).toHaveCount(1);
  await expect(page.locator('#import-dialog')).toBeVisible();
  expect(analysisPGN).toBeUndefined();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete');
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  expect(analysisPGN).toBe(pgns[1]);
  expect(calls).toEqual([
    { username: 'Player' },
    { username: 'player', year: '2026', month: '10', page: '1' },
  ]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('browses game pages and months without leaving stale games on failure', async ({ page }) => {
  const calls = [];
  await page.route(endpoint, (route) => {
    const params = new URL(route.request().url()).searchParams;
    calls.push(Object.fromEntries(params));
    if (!params.has('month')) return route.fulfill({ json: archives });
    if (params.get('month') === '09') {
      return route.fulfill({ status: 503, json: { error: 'Unable to reach Chess.com.' } });
    }
    const number = Number(params.get('page'));
    return route.fulfill({ json: { username: 'player', page: number, pages: 2, total: 26, games: [games[number - 1]] } });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#games-page')).toHaveText('26 games · 1 / 2');
  await page.getByRole('button', { name: 'Next game page' }).click();
  await expect(page.locator('#games-page')).toHaveText('26 games · 2 / 2');
  await expect(page.locator('#chesscom-game option:checked')).toContainText('½–½');
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeEnabled();
  await page.getByRole('button', { name: 'Previous game page' }).click();
  await expect(page.locator('#games-page')).toHaveText('26 games · 1 / 2');
  await page.locator('#chesscom-month').selectOption('2026-09');
  await expect(page.locator('#chesscom-error')).toHaveText('Unable to reach Chess.com.');
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeDisabled();
  await expect(page.locator('#chesscom-game option')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Find games', exact: true })).toBeEnabled();
  expect(calls.at(-1)).toEqual({ username: 'player', year: '2026', month: '09', page: '1' });
});

test('defaults to the searched player perspective only after successful analysis', async ({ page }) => {
  const blackGame = {
    ...games[0], white: games[0].black, black: { ...games[0].white, username: 'pLaYeR' },
  };
  await page.route(endpoint, (route) => {
    const params = new URL(route.request().url()).searchParams;
    return route.fulfill({ json: params.has('month')
      ? { username: 'player', page: 1, pages: 1, total: 2, games: [blackGame, games[1]] }
      : archives });
  });
  let fail = false;
  await page.route('**/api/analyze/', (route) => route.fulfill(fail
    ? { status: 503, json: { error: 'Engine unavailable.' } }
    : { json: {
      headers: { White: 'White player', Black: 'Black player' }, moves: [],
      initial_fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      analysis_depth: 12, analysis_time_seconds: 0.2,
    } }));
  const board = page.locator('#board');
  await openLoader(page);
  await page.locator('#chesscom-username').fill('PLAYER');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-game option')).toHaveCount(2);
  await expect(board).toHaveClass(/orientation-white/);
  await page.getByRole('button', { name: 'Analyze game', exact: true }).click();
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(board).toHaveClass(/orientation-black/);
  await expect(page.locator('.board-shell + .player-card #black-player')).toBeVisible();
  await page.locator('#flip').click();
  await expect(board).toHaveClass(/orientation-white/);
  await expect(page.locator('.board-shell + .player-card #white-player')).toBeVisible();
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze game', exact: true }).click();
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(board).toHaveClass(/orientation-black/);
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.locator('#chesscom-game').selectOption('1');
  await expect(board).toHaveClass(/orientation-black/);
  fail = true;
  await page.getByRole('button', { name: 'Analyze game', exact: true }).click();
  await expect(page.locator('#import-error')).toHaveText('Engine unavailable.');
  await expect(board).toHaveClass(/orientation-black/);
  fail = false;
  await page.getByRole('button', { name: 'Analyze game', exact: true }).click();
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(board).toHaveClass(/orientation-white/);
  await expect(page.locator('.board-shell + .player-card #white-player')).toBeVisible();
  await page.locator('#flip').click();
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Use example game', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze game', exact: true }).click();
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(board).toHaveClass(/orientation-white/);
});

test('handles unknown users, empty archives, and months with no supported games', async ({ page }) => {
  await page.route(endpoint, (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get('username') === 'unknown') {
      return route.fulfill({ status: 404, json: { error: 'Chess.com could not find that player.' } });
    }
    if (params.get('username') === 'empty') {
      return route.fulfill({ json: { username: 'empty', archives: [] } });
    }
    return route.fulfill({ json: params.has('month')
      ? { username: 'player', page: 1, pages: 1, total: 0, games: [] }
      : archives });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('unknown');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-error')).toContainText('could not find');
  await page.locator('#chesscom-username').fill('empty');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-status')).toContainText('No completed-game archives');
  await expect(page.locator('#chesscom-picker')).toBeHidden();
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-status')).toContainText('No completed standard or Chess960 games');
  await expect(page.locator('#chesscom-month')).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeDisabled();
});

test('labels and analyzes a selected Chess960 game with the local engine', async ({ page }) => {
  test.skip(process.env.CHESS_ANALYZER_RUN_ENGINE_TESTS !== '1', 'Requires installed Stockfish.');
  const fen = '4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1';
  const pgn = `[Variant "Chess960"]\n[SetUp "1"]\n[FEN "${fen}"]\n\n1. O-O *`;
  await page.route(endpoint, (route) => {
    const params = new URL(route.request().url()).searchParams;
    return route.fulfill({ json: params.has('month')
      ? { username: 'player', page: 1, pages: 1, total: 1, games: [{ ...games[0], rules: 'chess960', pgn }] }
      : archives });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-game option:checked')).toContainText('Chess960');
  await page.getByRole('button', { name: 'Analyze game', exact: true }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete', { timeout: 30_000 });
  await expect(page.locator('#board')).toHaveAttribute('data-fen', fen);
  await page.getByRole('button', { name: 'Last move', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', '4k3/8/8/8/8/8/8/R4RK1 b - - 1 1');
});

test('editing the username cancels pending results and invalidates old selections', async ({ page }) => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  await page.route(endpoint, async (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get('username') === 'oldplayer') {
      await pending;
      return route.fulfill({ json: { ...archives, username: 'oldplayer' } });
    }
    return route.fulfill({ json: params.has('month')
      ? { username: 'player', page: 1, pages: 1, total: 2, games }
      : archives });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('oldplayer');
  const requested = page.waitForRequest((req) => req.url().includes('username=oldplayer'));
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await requested;
  await page.locator('#chesscom-username').fill('Player');
  await expect(page.getByRole('button', { name: 'Find games', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  release();
  await expect(page.locator('#chesscom-game option')).toHaveCount(2);
  await expect(page.locator('#chesscom-status')).toBeHidden();
  await page.locator('#chesscom-username').fill('different');
  await expect(page.locator('#chesscom-picker')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeDisabled();
});

test('pending month changes clear the old game before lookup finishes', async ({ page }) => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  let analyses = 0;
  await page.route('**/api/analyze/', (route) => {
    analyses++;
    return route.fulfill({ status: 503, json: { error: 'Unexpected analysis.' } });
  });
  await page.route(endpoint, async (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (!params.has('month')) return route.fulfill({ json: archives });
    if (params.get('month') === '09') {
      await pending;
      return route.fulfill({ status: 503, json: { error: 'Month lookup failed.' } });
    }
    return route.fulfill({ json: { username: 'player', page: 1, pages: 1, total: 2, games } });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeEnabled();
  await page.locator('#chesscom-month').selectOption('2026-09');
  await expect(page.locator('#chesscom-form')).toHaveAttribute('aria-busy', 'true');
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeDisabled();
  await expect(page.locator('#chesscom-game option')).toHaveCount(0);
  await page.locator('#analysis-form').evaluate((form) => form.requestSubmit());
  release();
  await expect(page.locator('#chesscom-error')).toHaveText('Month lookup failed.');
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeDisabled();
  expect(analyses).toBe(0);
});

test('analysis locks the current selection, rejects duplicate submits, and allows retry', async ({ page }) => {
  await page.route(endpoint, (route) => {
    const params = new URL(route.request().url()).searchParams;
    return route.fulfill({ json: params.has('month')
      ? { username: 'player', page: 1, pages: 1, total: 2, games }
      : archives });
  });
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const submitted = [];
  await page.route('**/api/analyze/', async (route) => {
    submitted.push(route.request().postDataJSON().pgn);
    await pending;
    return route.fulfill({ status: 503, json: { error: 'Engine unavailable. Try again.' } });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-game option')).toHaveCount(2);
  await page.locator('#chesscom-game').selectOption('1');
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.getByRole('button', { name: 'Analyzing…' })).toBeDisabled();
  for (const id of ['chesscom-username', 'chesscom-game', 'chesscom-month', 'chesscom-search', 'demo']) {
    await expect(page.locator(`#${id}`)).toBeDisabled();
  }
  await page.locator('#analysis-form').evaluate((form) => form.requestSubmit());
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Analyzing…' })).toBeDisabled();
  release();
  await expect(page.locator('#import-error')).toHaveText('Engine unavailable. Try again.');
  expect(submitted).toEqual([pgns[1]]);
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeEnabled();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect.poll(() => submitted.length).toBe(2);
  expect(submitted).toEqual([pgns[1], pgns[1]]);
});

test('selecting the example cancels lookup without letting late results replace it', async ({ page }) => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  await page.route(endpoint, async (route) => {
    await pending;
    return route.fulfill({ json: archives });
  });
  let submitted;
  await page.route('**/api/analyze/', (route) => {
    submitted = route.request().postDataJSON().pgn;
    return route.fulfill({ status: 503, json: { error: 'Test engine unavailable.' } });
  });
  await openLoader(page);
  await page.locator('#chesscom-username').fill('Player');
  const requested = page.waitForRequest((request) => endpoint.test(request.url()));
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await requested;
  await page.getByRole('button', { name: 'Use example game' }).click();
  release();
  await expect(page.locator('#import-status')).toContainText('Fool’s mate');
  await expect(page.locator('#chesscom-picker')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeEnabled();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#import-error')).toHaveText('Test engine unavailable.');
  expect(submitted).toContain('1. f3 e5 2. g4 Qh4#');
});
