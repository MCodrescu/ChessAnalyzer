"""Validated local-engine configuration and explicit environment loading."""

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

ENGINE_PATH_ENV: Final = "STOCKFISH_PATH"
DEPTH_ENV: Final = "STOCKFISH_DEPTH"
TIMEOUT_ENV: Final = "STOCKFISH_TIMEOUT_SECONDS"
ANALYSIS_TIME_ENV: Final = "STOCKFISH_TIME_SECONDS"
THREADS_ENV: Final = "STOCKFISH_THREADS"
HASH_ENV: Final = "STOCKFISH_HASH_MB"
LOCAL_ENV_FILE: Final = Path(".env")
DEFAULT_DEPTH: Final = 12
DEFAULT_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_ANALYSIS_TIME_SECONDS: Final = 0.2
DEFAULT_THREADS: Final = 1
DEFAULT_HASH_MB: Final = 64
CHESSCOM_USERNAME: Final = "MCodr"
CHESSCOM_USER_AGENT: Final = "ChessAnalyzer/0.1 (Chess.com user MCodr)"
CHESSCOM_RULES: Final = "chess"


class ConfigurationError(ValueError):
    """Application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Resource limits for one reusable Stockfish process.

    Args:
        stockfish_path: Executable path/name, not a shell command. None discovers
            Stockfish on PATH or in common Linux package locations at startup.
        analysis_depth: Maximum search depth, from 1 to 128; None is timed-only.
        analysis_time_seconds: Search time cap per position; None is depth-only.
        engine_timeout_seconds: Positive protocol/startup timeout. Search time is
            added to this allowance by python-chess when a time cap is enabled.
        threads: Engine search threads, from 1 to 1024. Match your CPU allocation.
        hash_mb: Engine hash table in MiB, from 1 to 1048576; allow extra RAM for
            the engine itself and Python. The engine also validates its limits.

    Raises:
        ConfigurationError: A value is invalid.
    """

    stockfish_path: str | None = None
    analysis_depth: int | None = DEFAULT_DEPTH
    analysis_time_seconds: float | None = DEFAULT_ANALYSIS_TIME_SECONDS
    engine_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    threads: int = DEFAULT_THREADS
    hash_mb: int = DEFAULT_HASH_MB

    def __post_init__(self) -> None:
        if self.stockfish_path is not None and (
            not isinstance(self.stockfish_path, str)
            or not self.stockfish_path.strip()
            or "\x00" in self.stockfish_path
        ):
            raise ConfigurationError(f"{ENGINE_PATH_ENV} must be an executable path.")
        self._validate_search_limits()

    def _validate_search_limits(self) -> None:
        """Reject invalid resources and unbounded searches.

        Args:
            None.

        Returns:
            None; invalid limits raise ConfigurationError.
        """
        if self.analysis_depth is None and self.analysis_time_seconds is None:
            raise ConfigurationError("A depth or analysis time is required.")
        for name, value, maximum in (
            (DEPTH_ENV, self.analysis_depth, 128),
            (THREADS_ENV, self.threads, 1024),
            (HASH_ENV, self.hash_mb, 1048576),
        ):
            if name == DEPTH_ENV and value is None:
                continue
            if type(value) is not int or not 1 <= value <= maximum:
                raise ConfigurationError(
                    f"{name} must be an integer from 1 to {maximum}."
                )
        self._validate_search_times()

    def _validate_search_times(self) -> None:
        """Require positive finite protocol and enabled search time limits.

        Args:
            None.

        Returns:
            None; invalid times raise ConfigurationError.
        """
        for name, value in (
            (TIMEOUT_ENV, self.engine_timeout_seconds),
            (ANALYSIS_TIME_ENV, self.analysis_time_seconds),
        ):
            if name == ANALYSIS_TIME_ENV and value is None:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ConfigurationError(f"{name} must be positive and finite.")


def _optional_int(name: str, default: int) -> int:
    text = os.getenv(name, "").strip()
    try:
        return int(text) if text else default
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer.") from None


def _optional_float(name: str, default: float) -> float:
    text = os.getenv(name, "").strip()
    try:
        return float(text) if text else default
    except ValueError:
        raise ConfigurationError(f"{name} must be a number.") from None


def load_settings(env_path: str | Path | None = None) -> Settings:
    """Read process settings, optionally loading an explicit dotenv file first.

    Existing environment values take precedence, including blank values (which
    select defaults). No file discovery, engine startup, or import-time I/O occurs.
    Missing files are allowed. Dotenv loading adds variables to os.environ.

    Args:
        env_path: Optional local dotenv file; None reads only the environment.

    Returns:
        Immutable engine settings; no API key is needed.

    Raises:
        ConfigurationError: Values are invalid or the file cannot be read.
    """
    if env_path is not None:
        try:
            load_dotenv(dotenv_path=env_path, override=False)
        except (OSError, UnicodeError):
            raise ConfigurationError("Unable to read the environment file.") from None
    time_text = os.getenv(ANALYSIS_TIME_ENV, "").strip().lower()
    return Settings(
        stockfish_path=os.getenv(ENGINE_PATH_ENV, "").strip() or None,
        analysis_depth=_optional_int(DEPTH_ENV, DEFAULT_DEPTH),
        analysis_time_seconds=(
            None
            if time_text == "none"
            else _optional_float(ANALYSIS_TIME_ENV, DEFAULT_ANALYSIS_TIME_SECONDS)
        ),
        engine_timeout_seconds=_optional_float(TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS),
        threads=_optional_int(THREADS_ENV, DEFAULT_THREADS),
        hash_mb=_optional_int(HASH_ENV, DEFAULT_HASH_MB),
    )
