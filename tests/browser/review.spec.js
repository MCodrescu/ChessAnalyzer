import { test, expect } from '@playwright/test';

const start = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const afterE4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';
const afterE5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2';
const afterD4 = 'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1';
const evaluation = (cp) => ({ cp, mate: null, terminal_result: null });
const payload = {
  initial_fen: start,
  headers: { White: '<img src=x onerror=alert(1)>', Black: 'Bob', Result: '*', Event: 'Browser test' },
  analysis_depth: 12,
  analysis_time_seconds: 0.2,
  moves: [
    { ply: 1, fullmove_number: 1, player: 'white', fen_before: start, fen_after: afterE4, best_fen: afterD4, played_move_uci: 'e2e4', played_move_san: 'e4', best_move_uci: 'd2d4', best_move_san: 'd4', evaluation_before: evaluation(25), evaluation_after: evaluation(-10), estimated_cp_loss: 35, is_best_move: false },
    { ply: 2, fullmove_number: 1, player: 'black', fen_before: afterE4, fen_after: afterE5, best_fen: afterE5, played_move_uci: 'e7e5', played_move_san: 'e5', best_move_uci: 'e7e5', best_move_san: 'e5', evaluation_before: evaluation(-10), evaluation_after: evaluation(0), estimated_cp_loss: 0, is_best_move: true },
  ],
};

async function loadReview(page) {
  await page.route('**/api/analyze/', async (route) => {
    expect(route.request().headers()['x-csrftoken']).toBeTruthy();
    expect(route.request().postDataJSON().pgn).toContain('f3');
    await route.fulfill({ json: payload });
  });
  await page.goto('/');
  await expect(page.locator('#board piece')).toHaveCount(32);
  await page.getByRole('button', { name: 'Load example game' }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete');
}

test('renders a local board with a responsive layout and real piece images', async ({ page }, testInfo) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('#board piece')).toHaveCount(32);
  expect(await page.locator('#board piece').first().evaluate((piece) => getComputedStyle(piece).backgroundImage)).toContain('data:image/svg');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
  await page.screenshot({ path: `test-results/review-${testInfo.project.name}.png`, fullPage: true });
});

test('reviews moves, compares arrows, previews both positions, and flips', async ({ page }) => {
  await loadReview(page);
  await expect(page.locator('#played-move')).toHaveText('e4');
  await expect(page.locator('#best-move')).toHaveText('d4');
  await expect(page.locator('#evaluation')).toHaveText('+0.25');
  await expect(page.locator('#board svg.cg-shapes line')).toHaveCount(2);
  await expect(page.locator('#white-player img')).toHaveCount(0);
  await expect(page.locator('#white-player')).toHaveText(payload.headers.White);
  await page.getByRole('button', { name: 'Played line', exact: true }).click();
  await expect(page.locator('#evaluation')).toHaveText('-0.10');
  await expect(page.locator('#board svg.cg-shapes line')).toHaveCount(0);
  await expect(page.locator('#board square.last-move')).toHaveCount(2);
  await page.getByRole('button', { name: 'Best line', exact: true }).click();
  await expect(page.locator('#evaluation')).toHaveText('Not searched');
  await expect(page.locator('#preview-note')).toContainText('one-move preview');
  await page.getByRole('button', { name: '1… e5, black', exact: true }).click();
  await expect(page.locator('#quality')).toHaveText('ENGINE MATCH');
  await expect(page.locator('#board svg.cg-shapes line')).toHaveCount(1);
  await expect(page.locator('#move-counter')).toHaveText('2 / 2');
  await expect(page.getByRole('button', { name: 'Next move', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Previous move', exact: true }).click();
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
  await page.getByRole('button', { name: 'Flip' }).click();
  await expect(page.locator('#board')).toHaveClass(/orientation-black/);
});

test('keyboard navigation ignores the PGN text field', async ({ page }) => {
  await loadReview(page);
  await page.locator('#pgn').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
  await page.locator('#pgn').blur();
  await page.keyboard.press('End');
  await expect(page.locator('#move-counter')).toHaveText('2 / 2');
  await page.keyboard.press('Home');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
});

test('file import, server errors, and empty games are handled', async ({ page }) => {
  await page.goto('/');
  await page.locator('#pgn-file').setInputFiles({ name: 'game.pgn', mimeType: 'text/plain', buffer: Buffer.from('1. e4 *') });
  await expect(page.locator('#pgn')).toHaveValue('1. e4 *');
  await page.route('**/api/analyze/', (route) => route.fulfill({ status: 429, json: { error: 'An analysis is already running.' } }));
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.getByRole('alert')).toHaveText('An analysis is already running.');
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeEnabled();
  await page.unroute('**/api/analyze/');
  await page.route('**/api/analyze/', (route) => route.fulfill({ json: { ...payload, moves: [] } }));
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#move-counter')).toHaveText('No moves');
  await expect(page.locator('#best-move')).toHaveText('—');
  await expect(page.getByRole('button', { name: 'Best line', exact: true })).toBeDisabled();
});

test('real Stockfish analysis works through the complete browser workflow', async ({ page }) => {
  test.skip(process.env.CHESS_ANALYZER_RUN_ENGINE_TESTS !== '1', 'Opt-in local Stockfish test');
  await page.goto('/');
  await expect(page.locator('#board piece')).toHaveCount(32);
  await page.getByRole('button', { name: 'Load example game' }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete', { timeout: 30_000 });
  await expect(page.locator('#move-list button')).toHaveCount(4);
  await page.getByRole('button', { name: 'Last move', exact: true }).click();
  await expect(page.locator('#played-move')).toHaveText('Qh4#');
  await page.getByRole('button', { name: 'Played line', exact: true }).click();
  await expect(page.locator('#evaluation')).toHaveText('0-1');
});
