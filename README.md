# ChessAnalyzer

Analyze standard-chess PGNs with a **local Stockfish engine**, not a remote
evaluation API. Python communicates with an OS-installed executable over UCI via
python-chess. No Stockfish API key, HTTP rate limits, or committed engine binaries.
Chess.com's public API is still used only to download games in the notebook.

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
starts over. Chess960 and other variants are excluded. The username, rules filter,
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