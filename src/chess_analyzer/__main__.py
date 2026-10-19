"""Command-line analysis and live engine installation checks."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import chess

from chess_analyzer import (
    ConfigurationError,
    InvalidPGNError,
    PGNAnalyzer,
    StockfishClient,
    StockfishEngineError,
    load_settings,
)


def main(argv: list[str] | None = None) -> int:
    """Analyze a PGN file or check the live engine, printing JSON to stdout.

    Args:
        argv: Optional CLI arguments; None reads the process command line.

    Returns:
        Zero on success, one on configuration/file/engine/PGN failure. Argument
        errors are reported by argparse with exit status two.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pgn", nargs="?", type=Path, help="One standard-chess or Chess960 PGN file"
    )
    parser.add_argument(
        "--check-engine", action="store_true", help="Search the start FEN"
    )
    parser.add_argument("--env-file", type=Path, help="Explicit optional dotenv file")
    args = parser.parse_args(argv)
    if (args.pgn is not None) == args.check_engine:
        parser.error("Supply either a PGN file or --check-engine.")
    try:
        settings = load_settings(args.env_file)
        pgn = args.pgn.read_text(encoding="utf-8") if args.pgn is not None else None
        with StockfishClient(settings) as client:
            result = (
                PGNAnalyzer(client).analyze(pgn)
                if pgn is not None
                else client.evaluate(chess.STARTING_FEN)
            )
        print(json.dumps(asdict(result), indent=2))
    except (
        ConfigurationError,
        InvalidPGNError,
        StockfishEngineError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"Analysis failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
