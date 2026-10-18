"""Single source of application settings, defaults, and environment loading."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

API_KEY_ENV: Final = "STOCKFISH_API_KEY"
DEPTH_ENV: Final = "STOCKFISH_DEPTH"
TIMEOUT_ENV: Final = "STOCKFISH_TIMEOUT_SECONDS"
LOCAL_ENV_FILE: Final = Path(".env")
STOCKFISH_API_URL: Final = "https://stockfish.online/api/s/v2.php"
MIN_DEPTH: Final = 1
MAX_DEPTH: Final = 15
DEFAULT_DEPTH: Final = 12
DEFAULT_TIMEOUT_SECONDS: Final = 30.0


class ConfigurationError(ValueError):
    """Application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated configuration shared by application components.

    Args:
        stockfish_api_key: Provider credential, excluded from representations.
        analysis_depth: Search depth supported by the provider.
        request_timeout_seconds: Positive finite HTTP connect/read timeout.

    Raises:
        ConfigurationError: A setting is invalid. Values are never echoed.
    """

    stockfish_api_key: str = field(repr=False)
    analysis_depth: int = DEFAULT_DEPTH
    request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    stockfish_api_url: str = field(default=STOCKFISH_API_URL, init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.stockfish_api_key, str)
            or not self.stockfish_api_key.strip()
        ):
            raise ConfigurationError(f"{API_KEY_ENV} must be a nonblank string.")
        if (
            type(self.analysis_depth) is not int
            or not MIN_DEPTH <= self.analysis_depth <= MAX_DEPTH
        ):
            raise ConfigurationError(
                f"{DEPTH_ENV} must be an integer from {MIN_DEPTH} to {MAX_DEPTH}."
            )
        timeout = self.request_timeout_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ConfigurationError(f"{TIMEOUT_ENV} must be positive and finite.")


def load_settings(env_path: str | Path | None = None) -> Settings:
    """Load settings once at startup, optionally reading an explicit dotenv file.

    Existing environment values take precedence over dotenv values. With no
    path, only the process environment is read; there is no file discovery or
    import-time I/O. Missing files are allowed if the environment supplies a key.

    Args:
        env_path: Local dotenv file to load, or None for environment only.

    Returns:
        Immutable validated settings.

    Raises:
        ConfigurationError: Configuration cannot be loaded or is invalid.

    Side effects:
        Adds dotenv variables to os.environ without overriding existing values.
    """
    if env_path is not None:
        try:
            load_dotenv(dotenv_path=env_path, override=False)
        except (OSError, UnicodeError):
            raise ConfigurationError("Unable to read the environment file.") from None

    depth_text = os.getenv(DEPTH_ENV, "").strip()
    timeout_text = os.getenv(TIMEOUT_ENV, "").strip()
    try:
        depth = int(depth_text) if depth_text else DEFAULT_DEPTH
    except ValueError:
        raise ConfigurationError(f"{DEPTH_ENV} must be an integer.") from None
    try:
        timeout = float(timeout_text) if timeout_text else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        raise ConfigurationError(f"{TIMEOUT_ENV} must be a number.") from None
    return Settings(
        stockfish_api_key=os.getenv(API_KEY_ENV, ""),
        analysis_depth=depth,
        request_timeout_seconds=timeout,
    )
