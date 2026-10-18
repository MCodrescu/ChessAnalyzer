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
  await page.goto('/');
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-game option')).toHaveCount(2);
  await expect(page.locator('#chesscom-game option').first()).toContainText('Player (1400) vs Opponent (1450)');
  await expect(page.locator('#chesscom-game option').first()).toContainText('1–0');
  await expect(page.locator('#chesscom-game option').last()).toContainText('½–½');
  await page.locator('#chesscom-game').selectOption('1');
  await page.getByRole('button', { name: 'Load selected game' }).click();
  await expect(page.locator('#pgn')).toHaveValue(pgns[1]);
  expect(analysisPGN).toBeUndefined();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete');
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
  await page.goto('/');
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#games-page')).toHaveText('26 games · 1 / 2');
  await page.getByRole('button', { name: 'Next game page' }).click();
  await expect(page.locator('#games-page')).toHaveText('26 games · 2 / 2');
  await page.getByRole('button', { name: 'Load selected game' }).click();
  await expect(page.locator('#pgn')).toHaveValue(pgns[1]);
  await page.getByRole('button', { name: 'Previous game page' }).click();
  await expect(page.locator('#games-page')).toHaveText('26 games · 1 / 2');
  await page.locator('#chesscom-month').selectOption('2026-09');
  await expect(page.locator('#chesscom-error')).toHaveText('Unable to reach Chess.com.');
  await expect(page.getByRole('button', { name: 'Load selected game' })).toBeDisabled();
  await expect(page.locator('#chesscom-game option')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Find games', exact: true })).toBeEnabled();
  expect(calls.at(-1)).toEqual({ username: 'player', year: '2026', month: '09', page: '1' });
});

test('handles unknown users, empty archives, and months with no standard games', async ({ page }) => {
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
  await page.goto('/');
  await page.locator('#chesscom-username').fill('unknown');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-error')).toContainText('could not find');
  await page.locator('#chesscom-username').fill('empty');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-status')).toContainText('No completed-game archives');
  await expect(page.locator('#chesscom-picker')).toBeHidden();
  await page.locator('#chesscom-username').fill('Player');
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await expect(page.locator('#chesscom-status')).toContainText('No completed standard games');
  await expect(page.locator('#chesscom-month')).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Load selected game' })).toBeDisabled();
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
  await page.goto('/');
  await page.locator('#chesscom-username').fill('oldplayer');
  const requested = page.waitForRequest((req) => req.url().includes('username=oldplayer'));
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  await requested;
  await page.locator('#chesscom-username').fill('Player');
  await expect(page.getByRole('button', { name: 'Find games', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Find games', exact: true }).click();
  release();
  await expect(page.locator('#chesscom-status')).toContainText('Choose a game for player');
  await expect(page.locator('#chesscom-game option')).toHaveCount(2);
  await page.locator('#chesscom-username').fill('different');
  await expect(page.locator('#chesscom-picker')).toBeHidden();
  await expect(page.locator('#chesscom-load')).toBeDisabled();
});
