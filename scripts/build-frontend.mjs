// Keep all board assets local; no CDN requests or runtime Node server needed.
import { build } from 'esbuild';
import { cp, mkdir } from 'node:fs/promises';

const source = 'node_modules/@lichess-org/chessground';
const target = 'src/chess_analyzer/web/static/review/vendor';
await mkdir(target, { recursive: true });
await build({
  entryPoints: [`${source}/dist/chessground.js`],
  outfile: `${target}/chessground.js`,
  bundle: true,
  format: 'esm',
  minify: true,
  legalComments: 'eof',
});
await cp(`${source}/assets`, `${target}/assets`, { recursive: true });
await cp(`${source}/LICENSE`, `${target}/CHESSGROUND-LICENSE`);
await cp(`${source}/README.md`, `${target}/CHESSGROUND-README.md`);
await build({
  entryPoints: ['src/chess_analyzer/web/static/review/board-rules.js'],
  outfile: `${target}/board-rules.js`,
  bundle: true,
  format: 'esm',
  minify: true,
  legalComments: 'eof',
});
await cp('node_modules/chessops/LICENSE.txt', `${target}/CHESSOPS-LICENSE`);