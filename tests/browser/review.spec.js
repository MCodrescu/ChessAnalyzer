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

async function loadReview(page, review = payload) {
  await page.route('**/api/analyze/', async (route) => {
    expect(route.request().headers()['x-csrftoken']).toBeTruthy();
    expect(route.request().postDataJSON().pgn).toContain('f3');
    await route.fulfill({ json: review });
  });
  await page.goto('/');
  await expect(page.locator('#board cg-board piece')).toHaveCount(32);
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Use example game' }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete');
}

async function squarePoint(page, square) {
  const board = page.locator('#board');
  const bounds = await board.boundingBox();
  const flipped = (await board.getAttribute('class')).includes('orientation-black');
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  return { x: (flipped ? 7 - file : file) * bounds.width / 8 + bounds.width / 16,
    y: (flipped ? rank : 7 - rank) * bounds.height / 8 + bounds.height / 16 };
}

async function clickMove(page, from, to) {
  await page.locator('#board').click({ position: await squarePoint(page, from) });
  await page.locator('#board').click({ position: await squarePoint(page, to) });
}

test('clicks legal moves before import, rejects illegal moves, and resets', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', start);
  await clickMove(page, 'e7', 'e5');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', start);
  await clickMove(page, 'e2', 'e5');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', start);
  await clickMove(page, 'e2', 'e4');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterE4);
  await expect(page.locator('#quality')).toHaveText('EXPLORING');
  await clickMove(page, 'e7', 'e5');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterE5);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterE4);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', start);
  await expect(page.locator('#reset-variation')).toBeDisabled();
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test('trial moves preserve review scores and return through undo, reset, and navigation', async ({ page }) => {
  await loadReview(page);
  const graph = await page.locator('#graph-line').getAttribute('d');
  await clickMove(page, 'd2', 'd4');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterD4);
  await expect(page.locator('#evaluation')).toHaveText('Not searched');
  await expect(page.locator('#preview-note')).toContainText('variation is not analyzed');
  await expect(page.locator('#graph-line')).toHaveAttribute('d', graph);
  await expect(page.locator('#white-accuracy')).toHaveText('87.5%');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
  await expect(page.locator('#board svg.cg-shapes line')).toHaveCount(0);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', start);
  await expect(page.locator('#evaluation')).toHaveText('+0.25');
  await expect(page.locator('#board svg.cg-shapes line')).toHaveCount(2);
  await page.getByRole('button', { name: 'Played line', exact: true }).click();
  await page.getByRole('button', { name: 'Flip' }).click();
  await clickMove(page, 'e7', 'e5');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterE5);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterE4);
  await expect(page.locator('#evaluation')).toHaveText('-0.10');
  await clickMove(page, 'e7', 'e5');
  await page.getByRole('button', { name: 'Next move', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterE4);
  await expect(page.locator('#quality')).toHaveText('ENGINE MATCH');
  await expect(page.locator('#undo-variation')).toBeDisabled();
});

test('dragging a piece plays a legal move', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile', 'Mouse dragging is a desktop gesture; mobile uses tap-to-move.');
  await loadReview(page);
  const board = await page.locator('#board').boundingBox();
  const from = await squarePoint(page, 'e2');
  const to = await squarePoint(page, 'e4');
  await page.mouse.move(board.x + from.x, board.y + from.y);
  await page.mouse.down();
  await page.mouse.move(board.x + to.x, board.y + to.y, { steps: 10 });
  await page.mouse.up();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', afterE4);
});

test('handles castling, en passant, promotion cancellation and underpromotion', async ({ page }) => {
  async function position(fen) {
    await loadReview(page, { ...payload, initial_fen: fen, moves: [] });
  }
  await position('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1');
  await clickMove(page, 'e1', 'g1');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', 'r3k2r/8/8/8/8/8/8/R4RK1 b kq - 1 1');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', 'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1');
  await position('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2');
  await clickMove(page, 'e5', 'd6');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', '4k3/8/3P4/8/8/8/8/4K3 b - - 0 2');
  const promotion = '7k/P7/8/8/8/8/8/7K w - - 0 1';
  await position(promotion);
  await clickMove(page, 'a7', 'a8');
  await expect(page.getByRole('dialog', { name: 'Promote pawn' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', promotion);
  await clickMove(page, 'a7', 'a8');
  await page.getByRole('button', { name: 'Knight', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', 'N6k/8/8/8/8/8/8/7K b - - 0 1');
  await expect(page.locator('#promotion-dialog')).not.toBeVisible();
});

test('Chess960 review supports castling, preview navigation, undo and reset', async ({ page }) => {
  const fen = '4k3/8/8/8/8/8/8/R1K2R2 w KQ - 0 1';
  const after = '4k3/8/8/8/8/8/8/R4RK1 b - - 1 1';
  await loadReview(page, {
    ...payload, chess960: true, initial_fen: fen,
    moves: [{
      ...payload.moves[0], fen_before: fen, fen_after: after, best_fen: after,
      played_move_uci: 'c1f1', best_move_uci: 'c1f1', played_move_san: 'O-O',
      best_move_san: 'O-O', is_best_move: true,
    }],
  });
  await clickMove(page, 'c1', 'f1');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', after);
  await expect(page.locator('#position-label')).toContainText('O-O');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', fen);
  await clickMove(page, 'c1', 'a1');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', '4k3/8/8/8/8/8/8/2KR1R2 b - - 1 1');
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', fen);
  await page.getByRole('button', { name: 'Played line', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', after);
  await page.getByRole('button', { name: 'Best line', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', after);
  await expect(page.locator('#undo-variation')).toBeDisabled();
});

test('Chess960 castling swaps king and rook when their squares overlap', async ({ page }) => {
  const fen = '4k3/8/8/8/8/8/8/5KR1 w K - 0 1';
  await loadReview(page, { ...payload, chess960: true, initial_fen: fen, moves: [] });
  await clickMove(page, 'f1', 'g1');
  await expect(page.locator('#board')).toHaveAttribute('data-fen', '4k3/8/8/8/8/8/8/5RK1 b - - 1 1');
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('#board')).toHaveAttribute('data-fen', fen);
});

test('renders a local board with a responsive layout and real piece images', async ({ page }, testInfo) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('#board cg-board piece')).toHaveCount(32);
  expect(await page.locator('#board cg-board piece').first().evaluate((piece) => getComputedStyle(piece).backgroundImage)).toContain('data:image/svg');
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
  await expect(page.locator('.board-column > .player-card strong')).toHaveText([
    payload.headers.Black, payload.headers.White,
  ]);
  await page.getByRole('button', { name: 'Flip' }).click();
  await expect(page.locator('#board')).toHaveClass(/orientation-black/);
  await expect(page.locator('.board-column > .player-card strong')).toHaveText([
    payload.headers.White, payload.headers.Black,
  ]);
  await expect(page.locator('.board-column > .player-card').first().locator('.color-dot')).toHaveClass('color-dot white');
  await expect(page.locator('.board-column > .player-card').last().locator('.color-dot')).toHaveClass('color-dot black');
  await page.getByRole('button', { name: 'Flip' }).click();
  await expect(page.locator('#board')).toHaveClass(/orientation-white/);
  await expect(page.locator('.board-column > .player-card strong')).toHaveText([
    payload.headers.Black, payload.headers.White,
  ]);
});

test('shows estimated accuracy and a graph synchronized with actual game positions', async ({ page }, testInfo) => {
  await loadReview(page);
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(page.locator('#white-accuracy')).toHaveText(/\d+\.\d%/);
  await expect(page.locator('#white-accuracy')).toHaveText('87.5%');
  await expect(page.locator('#black-accuracy')).toHaveText('96.9%');
  await expect(page.locator('.summary-panel')).toContainText('LICHESS METHOD');
  await expect(page.locator('#white-accuracy-name')).toHaveText(payload.headers.White);
  await expect(page.locator('#white-accuracy-name img')).toHaveCount(0);
  await expect(page.locator('#graph-line')).toHaveAttribute('d', /^M.+L.+L/);
  await expect(page.locator('#graph-readout')).toHaveText('Start · +0.25');
  await page.screenshot({ path: `test-results/summary-${testInfo.project.name}.png`, fullPage: true });
  const originalLine = await page.locator('#graph-line').getAttribute('d');
  await page.getByRole('button', { name: 'Flip' }).click();
  await expect(page.locator('#graph-line')).toHaveAttribute('d', originalLine);

  const graph = page.locator('#evaluation-graph');
  const bounds = await graph.boundingBox();
  await graph.click({ position: { x: bounds.width - 10, y: bounds.height / 2 } });
  await expect(page.locator('#move-counter')).toHaveText('2 / 2');
  await expect(page.locator('#graph-readout')).toHaveText('1… e5 · +0.00');
  await expect(page.locator('#evaluation')).toHaveText('+0.00');
  await expect(page.locator('[data-preview="played"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#graph-position').focus();
  await page.keyboard.press('Home');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
  await expect(page.locator('[data-preview="before"]')).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#graph-readout')).toHaveText('1. e4 · -0.10');
  await expect(page.locator('#evaluation')).toHaveText('-0.10');
  await page.getByRole('button', { name: 'Best line', exact: true }).click();
  await expect(page.locator('#graph-note')).toContainText('Best-line preview is not plotted');
  await expect(page.locator('#graph-readout')).toHaveText('Start · +0.25');
  await expect(page.locator('#evaluation')).toHaveText('Not searched');
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test('game loader traps focus, dismisses with Escape, and preserves the review', async ({ page }) => {
  await loadReview(page);
  await page.getByRole('button', { name: 'Next move', exact: true }).click();
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Load a game' })).toBeVisible();
  await page.locator('#chesscom-username').fill('OtherPlayer');
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeDisabled();
  for (let index = 0; index < 12; index++) {
    await page.keyboard.press('Tab');
    expect(await page.locator('#import-dialog').evaluate((dialog) => dialog.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Load game', exact: true })).toBeFocused();
  await expect(page.locator('#move-counter')).toHaveText('2 / 2');
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await expect(page.locator('#chesscom-username')).toHaveValue('OtherPlayer');
  await expect(page.locator('#selected-game')).toContainText('Choose a game');
  await page.getByRole('button', { name: 'Close game loader' }).click();
  await expect(page.locator('#import-dialog')).not.toBeVisible();
});

test('failed imports preserve summary data and a later empty game clears it', async ({ page }) => {
  await loadReview(page);
  const accuracy = await page.locator('#white-accuracy').textContent();
  const line = await page.locator('#graph-line').getAttribute('d');
  await page.unroute('**/api/analyze/');
  await page.route('**/api/analyze/', (route) => route.fulfill({ status: 503, json: { error: 'Engine unavailable.' } }));
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#import-error')).toHaveText('Engine unavailable.');
  await expect(page.locator('#import-dialog')).toBeVisible();
  await expect(page.locator('#white-accuracy')).toHaveText(accuracy);
  await expect(page.locator('#graph-line')).toHaveAttribute('d', line);
  await page.unroute('**/api/analyze/');
  await page.route('**/api/analyze/', (route) => route.fulfill({ json: { ...payload, moves: [] } }));
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(page.locator('#white-accuracy')).toHaveText('—');
  await expect(page.locator('#graph-line')).toHaveAttribute('d', '');
  await expect(page.locator('#graph-empty')).toBeVisible();
});

test('analysis can finish after dismissing the loader without losing the current review', async ({ page }) => {
  await loadReview(page);
  await page.unroute('**/api/analyze/');
  let finish;
  const pending = new Promise((resolve) => { finish = resolve; });
  await page.route('**/api/analyze/', async (route) => {
    await pending;
    await route.fulfill({ json: { ...payload, headers: { White: 'Next player' }, moves: [payload.moves[0]] } });
  });
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#import-status')).toContainText('Stockfish is reviewing');
  await expect(page.getByRole('button', { name: 'Analyzing…' })).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(page.locator('#import-dialog')).not.toBeVisible();
  await expect(page.locator('#status')).toContainText('Stockfish is reviewing');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
  finish();
  await expect(page.locator('#status')).toContainText('Analysis complete');
  await expect(page.locator('#white-accuracy-name')).toHaveText('Next player');
  await expect(page.locator('#black-accuracy')).toHaveText('—');
  await expect(page.locator('#move-counter')).toHaveText('1 / 1');
  await expect(page.locator('#graph-position')).toHaveAttribute('max', '1');
  await expect(page.locator('#import-dialog')).not.toBeVisible();
});

test('workspace fits the viewport and keeps the board controls visible', async ({ page }, testInfo) => {
  await loadReview(page);
  const viewports = testInfo.project.name === 'mobile'
    ? [{ width: 390, height: 844 }, { width: 390, height: 664 }]
    : [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 1024, height: 768 }, { width: 900, height: 600 }];
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await expect(page.locator('.intro')).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => ({
      width: document.documentElement.scrollWidth <= window.innerWidth,
      height: document.documentElement.scrollHeight <= window.innerHeight,
    }))).toEqual({ width: true, height: true });
    const board = await page.locator('.board-shell').boundingBox();
    expect(board.y).toBeLessThan(110);
    expect(board.width).toBeGreaterThan(150);
    expect(board.width).toBeCloseTo(board.height, 0);
    const visibleSections = ['.board-shell', '.board-toolbar', '.board-caption', 'footer'];
    if (viewport.width > 850) {
      visibleSections.push('.summary-panel', '.comparison-panel', '.moves-panel');
    }
    for (const selector of visibleSections) {
      const bounds = await page.locator(selector).boundingBox();
      expect(bounds.y).toBeGreaterThanOrEqual(0);
      expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height);
    }
    // The sidebar remains usable without pushing the board or page down.
    await page.locator('.moves-panel').scrollIntoViewIfNeeded();
    await expect(page.locator('.moves-panel')).toBeInViewport();
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  }
});

test('player cards follow orientation before analysis and when a new game loads', async ({ page }) => {
  let headers = payload.headers;
  await page.route('**/api/analyze/', (route) => route.fulfill({ json: { ...payload, headers } }));
  await page.goto('/');
  await expect(page.locator('#board cg-board piece')).toHaveCount(32);
  await page.getByRole('button', { name: 'Flip' }).click();
  await expect(page.locator('.board-column > .player-card strong')).toHaveText(['White', 'Black']);
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Use example game' }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete');
  await expect(page.locator('.board-column > .player-card strong')).toHaveText([
    payload.headers.White, payload.headers.Black,
  ]);
  await page.getByRole('button', { name: 'Next move', exact: true }).click();
  await expect(page.locator('#board')).toHaveClass(/orientation-black/);
  headers = { White: 'New white player', Black: 'New black player' };
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('.board-column > .player-card strong')).toHaveText([
    headers.White, headers.Black,
  ]);
  await expect(page.locator('#board')).toHaveClass(/orientation-black/);
});

test('move navigation scrolls only the move list, not the page', async ({ page }) => {
  const moves = Array.from({ length: 80 }, (_, index) => ({
    ...payload.moves[index % 2],
    ply: index + 1,
    fullmove_number: Math.floor(index / 2) + 1,
  }));
  await loadReview(page, { ...payload, moves });
  await page.getByRole('button', { name: 'Next move', exact: true }).scrollIntoViewIfNeeded();
  const scrollY = await page.evaluate(() => window.scrollY);

  async function expectPageStill() {
    // Allow smooth scrolling to finish so an ancestor scroll cannot pass unnoticed.
    await page.evaluate(async () => {
      for (let frame = 0; frame < 40; frame++) {
        await new Promise(requestAnimationFrame);
      }
    });
    expect(await page.evaluate(() => window.scrollY)).toBeCloseTo(scrollY, 0);
  }

  await page.getByRole('button', { name: 'Next move', exact: true }).click();
  await expect(page.locator('#move-counter')).toHaveText('2 / 80');
  await expectPageStill();
  await page.getByRole('button', { name: 'Last move', exact: true }).click();
  await expect(page.locator('#move-counter')).toHaveText('80 / 80');
  await expectPageStill();
  expect(await page.locator('#move-list').evaluate((list) => list.scrollTop)).toBeGreaterThan(0);
  await page.keyboard.press('Home');
  await expect(page.locator('#move-counter')).toHaveText('1 / 80');
  await expectPageStill();
  expect(await page.locator('#move-list').evaluate((list) => list.scrollTop)).toBe(0);
  await page.keyboard.press('End');
  await expect(page.locator('#move-counter')).toHaveText('80 / 80');
  await expectPageStill();
  const selectedVisible = await page.locator('#move-list').evaluate((list) => {
    const selected = list.querySelector('[aria-current="true"]').getBoundingClientRect();
    const bounds = list.getBoundingClientRect();
    return selected.top >= bounds.top - 1 && selected.bottom <= bounds.bottom + 1;
  });
  expect(selectedVisible).toBe(true);
});

test('keyboard navigation ignores the game loader and username field', async ({ page }) => {
  await loadReview(page);
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.locator('#chesscom-username').focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
  await page.getByRole('button', { name: 'Close game loader' }).focus();
  await page.keyboard.press('End');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
  await page.keyboard.press('Escape');
  await page.keyboard.press('End');
  await expect(page.locator('#move-counter')).toHaveText('2 / 2');
  await page.keyboard.press('Home');
  await expect(page.locator('#move-counter')).toHaveText('1 / 2');
});

test('selected-game analysis handles server errors and empty games', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await expect(page.locator('#pgn, #pgn-file, textarea, input[type="file"]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeDisabled();
  await page.getByRole('button', { name: 'Use example game' }).click();
  await page.route('**/api/analyze/', (route) => route.fulfill({ status: 429, json: { error: 'An analysis is already running.' } }));
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toHaveText('An analysis is already running.');
  await expect(page.getByRole('button', { name: 'Analyze game' })).toBeEnabled();
  await page.unroute('**/api/analyze/');
  await page.route('**/api/analyze/', (route) => route.fulfill({ json: { ...payload, moves: [] } }));
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#move-counter')).toHaveText('No moves');
  await expect(page.locator('#best-move')).toHaveText('—');
  await expect(page.getByRole('button', { name: 'Best line', exact: true })).toBeDisabled();
  await expect(page.locator('#white-accuracy')).toHaveText('—');
  await expect(page.locator('#black-accuracy')).toHaveText('—');
  await expect(page.locator('#graph-line')).toHaveAttribute('d', '');
  await expect(page.locator('#graph-position')).toBeDisabled();
});

test('real Stockfish analysis works through the complete browser workflow', async ({ page }) => {
  test.skip(process.env.CHESS_ANALYZER_RUN_ENGINE_TESTS !== '1', 'Opt-in local Stockfish test');
  await page.goto('/');
  await expect(page.locator('#board cg-board piece')).toHaveCount(32);
  await page.getByRole('button', { name: 'Load game', exact: true }).click();
  await page.getByRole('button', { name: 'Use example game' }).click();
  await page.getByRole('button', { name: 'Analyze game' }).click();
  await expect(page.locator('#status')).toContainText('Analysis complete', { timeout: 30_000 });
  await expect(page.locator('#move-list button')).toHaveCount(4);
  await page.getByRole('button', { name: 'Last move', exact: true }).click();
  await expect(page.locator('#played-move')).toHaveText('Qh4#');
  await page.getByRole('button', { name: 'Played line', exact: true }).click();
  await expect(page.locator('#evaluation')).toHaveText('0-1');
  await expect(page.locator('#graph-readout')).toContainText('Qh4# · 0-1');
  await expect(page.locator('#white-accuracy')).toHaveText(/\d+\.\d%/);
});
