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
Left/right arrows navigate every actual game position, including the position
after the final move. **First**/**Home** return to the starting position;
**Last**/**End** show the final played position. **Previous**/**Left** from the
end return to the position before the final move. Clicking a move still opens
its **Before move** comparison, with **Next** available to play the last move.
At the final position, a **Game over** banner names the winner or draw and shows
the recorded result, including games decided off the board. If the record has
no result, it says **End of recorded game · Result unknown** instead of inferring
a winner from the engine evaluation. The banner disappears when navigating back
or exploring a new variation; terminal variations show their own result.
Imported games open with the searched
Chess.com player's color at the bottom (username matching is case-insensitive).
The player cards follow the board orientation. **Flip** switches sides manually;
loading another analysis restores that game's player perspective. The example
game defaults to White at the bottom.

Click a piece and then a highlighted destination, or drag it, to try legal moves
for either side from the displayed position (even before loading a game).
Castling, en passant, and a promotion-piece chooser are supported. **Undo** takes
back one trial move; **Reset** returns to the reviewed position. Selecting a game
move, preview tab, or graph position also discards the trial line. Trial moves
never change the imported game, accuracy, or graph. Each displayed trial position
is searched by local Stockfish: **Engine best** and the green arrow show its
recommended next move, with a White-relative evaluation. While exploring, the
surrounding game review is grayed out; the board and move insights remain clear
and interactive. **Searching…** indicates a pending search; failures are shown
with a **Retry engine search** button rather than a stale recommendation.
Rapid navigation discards outdated results and serializes position searches.
FEN-based searches do not include repetition history.

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
- **Played line** shows the actual resulting position and searches its next
  best move, rather than showing the recommendation for the preceding position.
- **Best line** previews the position after the recommendation, including
  castling and promotion. It enters the grayed variation mode and searches the
  resulting position for its evaluation and next best move. Play on the board
  to continue the variation, or use **Reset** to return to **Before move**.
- Evaluations favor White when positive. Loss is in centipawns from the moving
  player's perspective; mate transitions have no numeric CP loss. Depth/time
  displayed are requested search caps, not achieved depth.

This is a **local-first, synchronous MVP**: requests wait for the complete
analysis (roughly 20 seconds for 100 half-moves at default limits). Inputs are
limited to 100,000 characters / 600 half-moves and one running analysis per web
process; overlapping requests get HTTP 429. Engine resources come exclusively
from the server's `STOCKFISH_*` environment, not browser input. The web app does
not automatically load dotenv files; export environment values before starting.
`POST /api/position/` accepts a JSON `fen` (up to 200 characters) and an optional
boolean `chess960`, returning `fen`, `evaluation`, `best_move_uci`, and
`best_move_san`. Terminal positions return null best moves without starting an
engine. It requires CSRF protection and shares the game-analysis concurrency
limit and server-configured engine budgets.

For Codespaces/proxies, set `DJANGO_ALLOWED_HOSTS` to a comma-separated list of
trusted hostnames, and `DJANGO_CSRF_TRUSTED_ORIGINS` to comma-separated HTTPS
origins when needed. Do not use wildcard hosts or disable CSRF protection.
For deployment set `DJANGO_DEBUG=0`, a strong `DJANGO_SECRET_KEY`, and explicit
hosts/origins. The application is publicly accessible without authentication.
The Dockerfile now serves Django with Gunicorn and collected static files via
WhiteNoise. See [DigitalOcean App Platform](#digitalocean-app-platform) below.
Analysis is CPU-intensive: consider edge rate limits to reduce abuse and a background
queue with globally bounded engine concurrency before scaling to multiple workers
or instances. A web worker semaphore is not a cross-process job scheduler.
Cancelling a browser request does not stop an in-progress engine search.

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

## DigitalOcean App Platform

The default Docker build is a **web service**: Node builds the local board assets
in a separate stage, Debian installs Stockfish, and the final Python image runs
as an unprivileged user. No Node runtime, database, migrations, volume, or separate
static-site component is required. `collectstatic` runs during the build without
production secrets. Runtime secrets must not be passed as Docker build arguments.

### Create the app

1. Push this code to a GitHub repository accessible to your DigitalOcean account.
2. Use [.do/app.yaml](.do/app.yaml) as the App Platform specification template.
  Replace `YOUR_GITHUB_OWNER/YOUR_REPOSITORY` and adjust the branch and region.
  Alternatively, connect the repository in **Create App**, select the root
  Dockerfile, and copy the service settings and runtime variables from the spec.
3. Use a **web service** on port **8080**, initially **one instance with 1 GiB RAM**.
  Leave build/run command overrides empty so Docker's build and CMD are used.
  The plan in the template is paid; review current pricing before creating it.
4. Before deploying, set `DJANGO_SECRET_KEY` in the control panel to a unique random
  secret of at least 50 characters. Mark it **encrypted**, with **runtime** scope.
  Never commit the plaintext secret to the spec. A blank key intentionally prevents
  the production process from starting. No login credentials are needed; remove
  `DJANGO_BASIC_AUTH_USERNAME` and `DJANGO_BASIC_AUTH_PASSWORD` from older deployments.
5. Keep `DJANGO_ALLOWED_HOSTS=${APP_DOMAIN}` and
  `DJANGO_CSRF_TRUSTED_ORIGINS=${APP_URL}` as runtime bindable variables. DigitalOcean
  resolves them to the app's primary domain and HTTPS origin. For additional
  domains, append their exact hostnames/origins as comma-separated values; no `*`.
6. Keep `DJANGO_TRUST_PROXY=1` only behind App Platform's trusted ingress, which
  terminates TLS and sets `X-Forwarded-Proto`. Direct public access to the container
  must not be enabled. Production redirects HTTP to HTTPS and uses secure cookies.
7. Deploy and open the generated HTTPS URL; no login prompt is expected. Use the
  example game first, then try the Chess.com game picker.

The spec uses a **TCP** readiness check (no `http_path`), avoiding dependence on
the platform probe's Host header. `GET /healthz/` is also available
without authentication for an HTTP smoke check, returning `{"status":"ok"}`;
it does not test Stockfish or Chess.com. Test the installed engine from the app's
Console with `python -m chess_analyzer --check-engine` after deployment.

### Resource and security limits

Gunicorn runs one process with four threads: one engine job can run while other
threads handle health checks or return HTTP 429 for overlapping analysis requests.
Do not increase workers, enable autoscaling, or add instances without designing
global engine admission control. The template uses one engine thread, 64 MiB hash,
and a 0.1-second per-position search budget (rather than the local 0.2-second
default). Long games can still exceed ingress/client timeouts; reduce the search
budget or move analysis to queued jobs if that happens. Gunicorn's worker timeout
is a liveness setting, not a hard per-request deadline.

Django's `check --deploy` reports two intentional HSTS warnings: subdomain coverage
and preload are not enabled. Enable those only after confirming that every
subdomain you control supports HTTPS and deciding to join the browser preload list.

The review page and analysis APIs are public, with no login or shared password.
CSRF protection stays enabled, and analysis responses use `no-store`. There is no
per-client rate limiter: the concurrency limit bounds simultaneous engine jobs,
but it does not stop a visitor from making repeated requests or monopolizing the
engine. Consider edge rate limits for public traffic and monitor CPU usage.
PGNs/results are not persisted. In-memory caches reset on deployment. Review the
GPL and source-availability obligations in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before deployment/distribution.

### Local container smoke test

With Docker running, build and start the Linux web image from the repository root:

```bash
docker build -t chess-analyzer-web .
docker run --rm -p 8080:8080 --env-file .env.production chess-analyzer-web
```

Create the ignored local `.env.production` with `DJANGO_DEBUG=0`, production-style
`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1`, and
`DJANGO_CSRF_TRUSTED_ORIGINS=https://localhost`. Use an HTTPS reverse proxy for a
complete local production smoke test. A direct HTTP request to `/` should redirect;
`http://localhost:8080/healthz/` should return 200. Do not disable HTTPS for deployment.

After deployment, check `/healthz/` (200), `/` without credentials (200),
local board assets (200), example-game analysis, and Chess.com
lookup. HTTP 400 usually means an incorrect allowed host; CSRF 403 usually means
an incorrect HTTPS origin or proxy setting. Engine 503 means the engine/config
needs checking. HTTP 429 is expected when another analysis is running.

The CLI image remains available as an explicit build target:

```bash
docker build --target cli -t chess-analyzer-cli .
docker run --rm chess-analyzer-cli --check-engine
```

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