# ChessAnalyzer

Analyze standard-chess and Chess960 PGNs with a **local Stockfish engine**, not a remote
evaluation API. Python communicates with an OS-installed executable over UCI via
python-chess. No Stockfish API key, HTTP rate limits, or committed engine binaries.
Chess.com's public API is used only to download games in the notebook and web
game picker; all engine analysis stays local.

## Install and check the live engine

Ubuntu/Debian, including this dev container and an Ubuntu DigitalOcean Droplet:

```bash
bash scripts/install-stockfish.sh
```

The script runs `apt-get update` and `apt-get install -y --no-install-recommends
stockfish`, using sudo unless already root. The package normally installs under
/usr/games, **outside the repository**. It uses the distro's Stockfish version,
which may be older than the latest upstream release, and its appropriate CPU build.
On other OSes install a trusted native Stockfish build with that OS's package
manager, then configure `STOCKFISH_PATH` if needed. Do not put command-line flags
in that variable: it is an executable path/name, not a shell command.

Install Python dependencies (Python 3.11+), then run a real search:

```bash
python -m pip install -e '.[dev,notebook]'
python -m chess_analyzer --check-engine
```

The check prints JSON containing White-relative centipawns and a legal best move.
The Python dependency does **not** bundle Stockfish. Engine discovery tries PATH,
then /usr/games/stockfish and /usr/bin/stockfish. An explicit `STOCKFISH_PATH`
never falls back silently. No engine is downloaded or started during imports.

## Interface

### Django game review

The web application uses Lichess's **Chessground** board and the same local
analyzer as the CLI/notebook. Select **Load game** to open the game-loading modal.
Choose a Chess.com game and select **Analyze game**, then click any move. There
is no separate load/import step or manual PGN form. **Use example game** selects
a built-in sample without needing a Chess.com lookup. The modal closes after successful
analysis. Escape or the close button dismisses it without losing the current
review or game selection. Selecting a game never starts analysis by itself.
Left/right arrows navigate moves;
Home/End jump to the first/last move. The board can be flipped.

Click a piece and then a highlighted destination, or drag it, to try legal moves
for either side from the displayed position (even before loading a game).
Castling, en passant, and a promotion-piece chooser are supported. **Undo** takes
back one trial move; **Reset** returns to the reviewed position. Selecting a game
move, preview tab, or graph position also discards the trial line. Trial moves
never change the imported game, accuracy, or graph; their evaluation is marked
**Not searched**, because they are not sent to Stockfish.

Chess960 games use their PGN variant and starting FEN; no manual mode switch is
needed. Legal interactive moves use Chessops locally in the browser. To castle
in Chess960, move the king onto the participating rook (including when the king
or rook already occupies its final castling square). Castling arrows/highlights
use these same king-to-rook squares; SAN still displays `O-O` or `O-O-O`.
Standard chess retains king-to-destination-square castling.

The board and navigation fit the browser's viewport height. The review panels
show game accuracy, the evaluation graph, move insights, and the move list;
loading controls stay in the modal to save space. On desktop, the move list
scrolls within its panel; on phones, the review panels scroll below the board
without moving the board or the page.

#### Accuracy and evaluation graph

- **Game accuracy** uses the [Lichess accuracy
  algorithm](https://lichess.org/page/accuracy), verified against
  [lila revision 06ee345](https://github.com/lichess-org/lila/blob/06ee34552b24fa1a52e749d92fbc3a1ad37a5afb/modules/analyse/src/main/AccuracyPercent.scala),
  applied to this app's **local Stockfish evaluations**. Scores can differ from
  lichess.org because engine versions, search limits, and evaluations differ.
- Winning chances use White-relative evaluations capped at ±1000 centipawns:
  `50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1)`.
  Forced mates and terminal wins use the corresponding cap (approximately
  97.5%/2.5%, not 100%/0%); terminal draws use zero CP / 50% winning chances.
- For a positive loss `L` of the mover's winning-chance percentage points,
  move accuracy is
  `clamp(103.1668100711649 * exp(-0.04354415386753951 * L) - 3.166924740191411 + 1, 0, 100)`.
  The `+1` is Lichess's uncertainty bonus. No loss scores 100; matching the best
  move does **not** override an evaluation loss.
- Game accuracy is the average of a **volatility-weighted mean** and a
  **harmonic mean**, separately for each color. Window size is
  `clamp(floor(halfMoves / 10), 2, 8)` positions. The first full window is
  repeated `windowSize - 2` times before sliding; weights are population
  standard deviations of winning chances, clamped to `[0.5, 12]`. Harmonic-mean
  inputs are floored at 1, matching Lichess's implementation.
- The shared evaluation timeline contains the actual initial position and
  every actual post-move position, including custom FEN starts. A missing
  position invalidates any volatility window containing it, without shifting
  move colors. Games need scored moves for **both** colors to display game
  accuracy; empty or one-half-move games show dashes, matching Lichess.
- The **evaluation graph** plots the starting position and each actual move's
  resulting evaluation, always White-relative, regardless of board orientation.
  Positive values favor White. The display is capped at ±10 pawns; mate scores
  sit at the corresponding edge, while the readout retains the real score/mate.
  Click the graph or use its keyboard-accessible slider to jump to a position.
  Best-line previews are not plotted or given a fabricated evaluation.

```bash
python -m pip install -e '.[dev]'
npm ci
npm run build
python manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/. Stockfish must already be installed as described
above. Node/npm are build-time tools only. All board JavaScript, styles, and
piece images are served locally; no CDN or Lichess API is used. Rebuild after
changing frontend dependencies. Build before packaging a wheel so its static
assets are included. No database or migrations are needed, and PGNs/results are
not persisted; refreshing clears the review. Manual PGN paste/file import is not
part of the web interface; the CLI and JSON analysis API still accept PGNs.

#### Choose a Chess.com game

1. Select **Load game**, enter a **Chess.com username**, then select **Find games**
  (no login/API key).
2. The newest available archive month opens automatically. Choose another
  **Archive month** to browse older games.
3. Select a game. Lists show both players/ratings,
  local completion date/time, time control, and result. Games are newest first,
  with 25 per page; use the page arrows for more.
4. Select **Analyze game** to analyze the current selection directly. The button
  is disabled until a game is available, during lookup, and during analysis.
  Changing username, month, or page clears the old selection immediately so it
  cannot be analyzed accidentally. Selection changes never start engine analysis
  automatically or overwrite an existing review until the new analysis completes.

Only completed standard-chess and Chess960 games with nonempty PGNs within the
import-size limit are offered; live/in-progress games and other variants are
excluded. Chess960 entries are labeled in the game picker. An empty
month leaves the month picker available so you can choose an older archive.
Fetching needs internet and may lag behind Chess.com's cached public data;
Chess.com errors/rate limits are displayed in the modal; the current review
remains available, and the built-in example can be analyzed without a lookup.

Lookup makes one public API request at a time per web process, using the existing
Chess.com Python client (30-second HTTP timeout; no automatic retries). Public
archive/month data is cached **in process memory for 60 seconds**, not saved to
disk; analysis results are not cached. This is not a cross-process rate limiter.
The username is validated and upstream URLs are constructed by the client, never
taken from user input or followed from archive responses. Lookups begin only
when **Find games** is selected; typing alone sends no request. The browser does
not contact Chess.com directly and never requests a password.

- **Before move** shows both choices from the same position: green for the
  engine best move, blue for the played move (one green arrow when they match).
- **Played line** shows the actual resulting position and its evaluation.
- **Best line** previews the position after the recommendation, including
  castling and promotion. This is a one-move preview, not a searched principal
  variation; its resulting evaluation is deliberately not inferred.
- Evaluations favor White when positive. Loss is in centipawns from the moving
  player's perspective; mate transitions have no numeric CP loss. Depth/time
  displayed are requested search caps, not achieved depth.

This is a **local-first, synchronous MVP**: requests wait for the complete
analysis (roughly 20 seconds for 100 half-moves at default limits). Inputs are
limited to 100,000 characters / 600 half-moves and one running analysis per web
process; overlapping requests get HTTP 429. Engine resources come exclusively
from the server's `STOCKFISH_*` environment, not browser input. The web app does
not automatically load dotenv files; export environment values before starting.

For Codespaces/proxies, set `DJANGO_ALLOWED_HOSTS` to a comma-separated list of
trusted hostnames, and `DJANGO_CSRF_TRUSTED_ORIGINS` to comma-separated HTTPS
origins when needed. Do not use wildcard hosts or disable CSRF protection.
For deployment set `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, and explicit
hosts/origins; serve collected static files over HTTPS with a production server.
The existing Dockerfile still runs the CLI, not Django. Do not expose this
unauthenticated CPU-intensive endpoint publicly: add authentication, rate limits,
and a background queue with globally bounded engine concurrency first. A web
worker semaphore is not a cross-process job scheduler. Proxy/worker timeouts
must accommodate complete analyses; cancelling a browser request does not stop
an in-progress engine search.

Chessground is **GPL-3.0-or-later**, not permissively licensed. Review
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and upstream requirements before
distributing/deploying the combined app, including source-availability and
license/notice obligations. The build preserves upstream license and artwork
notices. No repository-wide relicensing is performed automatically.

Web validation uses the existing pytest suite plus `npm test` for presentation
helpers. Browser tests run with `npm run test:browser` after installing the
Playwright Chromium browser with `npx playwright install chromium`. Linux also
needs Playwright's system-library prerequisites. Set
`CHESS_ANALYZER_RUN_ENGINE_TESTS=1` to include the real-engine browser workflow;
otherwise browser tests mock the analysis response. `CHESS_ANALYZER_PYTHON` can
override the browser test server's default `.venv/bin/python` interpreter.

Use `StockfishClient(settings)` as a context manager, then pass it to
`PGNAnalyzer(client).analyze(pgn)`. `load_settings()` reads only the environment;
`load_settings(path)` optionally loads an explicit dotenv file. Defaults work
without any dotenv file or credential. See [.env.example](.env.example).

The client exposes `evaluate(fen)` and ordered `evaluate_many(fens)`. One process
is reused across all searches, retaining its hash table; batches are sequential,
not eight competing engine processes. Use Stockfish's own search threads for
parallelism. Do not share a client across concurrent calls; give each analysis
worker its own context-managed client and budget its resources separately.
`close()` is idempotent. Failed or closed clients must be replaced, not reused.
Engine discovery, startup, timeout, process, and result failures raise
`StockfishEngineError`. Invalid FEN/PGN input is rejected before searching.

For direct Chess960 position searches, pass `chess960=True` to either method;
FEN alone does not reliably identify the variant. PGN analysis carries this flag
automatically, and python-chess manages Stockfish's `UCI_Chess960` option. Results
include a `chess960` boolean; Chess960 UCI castling moves use king-to-rook notation.
Injected evaluators must accept the `chess960=True` keyword to analyze Chess960;
standard-game calls retain the original FEN-only calling convention.

CLI analysis accepts one PGN file and writes the complete result as JSON:

```bash
python -m chess_analyzer game.pgn
python -m chess_analyzer --env-file .env game.pgn
```

Use `--env-file` only for an explicit local configuration file. Existing process
environment values take precedence (including blank values selecting defaults).

### Search speed and resources

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `STOCKFISH_PATH` | auto | Trusted local executable path or name. |
| `STOCKFISH_DEPTH` | `12` | Maximum search depth, 1–128; not guaranteed reached. |
| `STOCKFISH_TIME_SECONDS` | `0.2` | Per-position search time cap; `none` searches by depth only. |
| `STOCKFISH_TIMEOUT_SECONDS` | `10` | Startup/protocol timeout allowance, not the search budget. |
| `STOCKFISH_THREADS` | `1` | Threads per engine; choose within your CPU allocation. |
| `STOCKFISH_HASH_MB` | `64` | Hash-table MiB per engine, not its total memory footprint. |

Search stops at the first depth/time limit. For a 100-half-move game, the default
search budget is roughly 101 × 0.2 = 20.2 seconds **plus startup and transport
overhead**; shallow positions may finish sooner. This is not a hard wall-time SLA.
For deeper analysis increase both depth and time. With time disabled, the protocol
timeout bounds a depth-only search; increase it for expensive searches.
`GameAnalysis.analysis_depth` and `analysis_time_seconds` record requested caps,
not achieved depth. `client.statistics` reports searches attempted and cumulative
search wall time, including failures; it does not report HTTP counters.

Scores are natively White-relative centipawns or signed mate distance. Automatic
terminal positions are resolved locally; PGN replay retains history for fivefold
draw detection. FEN-only evaluation cannot convey repetition history. Claimable
draws are not assumed claimed. Estimated CP loss is normalized to the moving
player, clamped at zero, and excludes mate-score transitions. Independent searches
are noisy: this is an estimate of move quality, **not an ELO prediction**.

## Latest-game notebook

Open [notebooks/analyze_latest_game.ipynb](notebooks/analyze_latest_game.ipynb),
select the project's virtual environment, and **restart the kernel after this
migration**. Run cells in order to fetch MCodr's latest completed standard-chess
game, analyze it locally, then view move comparisons and average CP loss.
The analysis cell loads the local dotenv file explicitly; no key is needed.
Fetching requires internet, but all engine searches are local. Rerunning analysis
starts over. The default `chess` rules filter excludes Chess960; use `chess960`
for Chess960 games or `None` for the latest supported game without filtering.
Other variants remain unsupported. The username, rules filter,
and User-Agent live in [src/chess_analyzer/config.py](src/chess_analyzer/config.py).
The notebook reports depth/time caps, resource settings, searches, and elapsed time.

## DigitalOcean deployment

### Ubuntu Droplet

Run the installer on the Droplet (or put the same apt commands in provisioning),
install the Python project in a virtual environment, then run the engine check.
Set `STOCKFISH_PATH=/usr/games/stockfish` in the worker/service environment if
needed; system services often have a restricted PATH. No binary is copied from
development and none is added to Git. Start with one search thread and 64 MiB hash
on a small Droplet; leave RAM for the engine's network, Python, and the OS.
Multiple simultaneous analysis workers multiply both CPU and memory use. Bound
job concurrency rather than starting an engine per HTTP request without limits.

### Container deployment

The [Dockerfile](Dockerfile) installs Stockfish via apt **during the image build**
and runs Python as a non-root user. [.dockerignore](.dockerignore) excludes local
secrets, downloaded engines, and development artifacts from the build context.

```bash
docker build -t chess-analyzer .
docker run --rm --cpus=1 --memory=512m chess-analyzer
docker run --rm --cpus=1 --memory=512m \
  -e STOCKFISH_THREADS=1 -e STOCKFISH_HASH_MB=64 \
  -v "$PWD/game.pgn:/data/game.pgn:ro" chess-analyzer /data/game.pgn
```

Use this image on a Droplet or as the basis of a DigitalOcean worker/job image.
It is a CLI/worker, **not a web service**: there is no HTTP listener for an App
Platform web-service health check. Supply your own job source/worker entrypoint
when integrating it into a service. Engine packages and any NNUE data belong in
the deployed image/system, not Git. [.gitignore](.gitignore) also excludes optional
engine-download directories and NNUE files. For reproducible scores, pin the
engine package/base image in your deployment; distro releases may differ. If you
redistribute engine-containing images, retain Stockfish's GPL notices and comply
with its corresponding-source obligations: see the
[official distribution guidance](https://stockfishchess.org/download/).

## Tests

```bash
python -m pytest
CHESS_ANALYZER_RUN_ENGINE_TESTS=1 python -m pytest -m integration
python -m ruff check .
python -m ruff format --check .
```

Unit tests mock the UCI boundary and forbid real engine startups and HTTP calls.
They cover process reuse/cleanup, timeouts/crashes, resource configuration, score
perspective, ordered batches, PGN edge cases, CLI output, and the offline notebook.
Integration tests are opt-in and need a system-installed Stockfish. They perform
real searches, verify legal moves and mate signs, and confirm process exit; they
skip when the engine is unavailable. They never download engines or call services.

### Migration from Stockfish Online

Replace `StockfishOnlineClient` with `StockfishClient` and `StockfishAPIError` with
`StockfishEngineError`. Remove `stockfish_api_key`, HTTP session injection, retry/
spacing options, and `max_workers` from `Settings`/client construction. Old API key,
retry, pacing, and worker environment variables are ignored and can be removed.
`STOCKFISH_TIMEOUT_SECONDS` now means the local protocol timeout; configure search
duration with `STOCKFISH_TIME_SECONDS`. HTTP statistics are replaced by
`EngineStatistics.positions` and `search_seconds`. Position/move result formats
remain unchanged; game results additionally record the requested time cap.