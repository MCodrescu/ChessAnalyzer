"""Bounded durable rating jobs shared by web processes and one engine worker."""

import json
import logging
import sqlite3
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from time import time
from typing import Literal
from uuid import uuid4

from django.conf import settings
from pydantic import BaseModel, FiniteFloat

logger = logging.getLogger(__name__)
EXPIRE_JOBS_SQL = "DELETE FROM rating_jobs WHERE expires <= ?"


class RatingResult(BaseModel):
    """Finite predictions and their serving provenance."""

    white: FiniteFloat
    black: FiniteFloat
    model_id: str
    model_version: str | None = None
    category: str | None = None
    analysis_key: str | None = None
    cache_hit: bool | None = None
    engine_compatibility: str
    engine_metadata: dict | None = None


class RatingJob(BaseModel):
    """Public job state, deliberately excluding the submitted PGN."""

    id: str
    status: Literal["queued", "running", "complete", "failed"]
    result: RatingResult | None = None
    error: str | None = None


class RatingQueueFull(ValueError):
    """The bounded queue has no room for another game."""


class RatingJobStore:
    """Keep short-lived jobs on local persistent storage, not process memory."""

    def __init__(self):
        """Initialize shared storage using deployment settings.

        Args:
            None.

        Returns:
            None; creates the database if needed.
        """
        self.path = Path(settings.RATING_JOB_DATABASE)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS rating_jobs "
                "(id TEXT PRIMARY KEY, status TEXT NOT NULL, pgn TEXT, "
                "result TEXT, error TEXT, expires REAL NOT NULL)"
            )

    @contextmanager
    def _connection(self):
        """Serialize short queue transactions across web and engine processes.

        Args:
            None.

        Returns:
            A transaction connection, closed after commit or rollback.
        """
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("PRAGMA secure_delete = ON")
                yield connection
        finally:
            connection.close()

    def submit(self, pgn: str) -> RatingJob:
        """Enqueue one validated game without starting an engine.

        Args:
            pgn: Validated original PGN, stored only until completion or expiry.

        Returns:
            The capability-ID and queued state; raises RatingQueueFull at capacity.
        """
        job = RatingJob(id=uuid4().hex, status="queued")
        with self._connection() as connection:
            connection.execute(EXPIRE_JOBS_SQL, (time(),))
            active = connection.execute(
                "SELECT count(*) FROM rating_jobs WHERE status IN ('queued', 'running')"
            ).fetchone()[0]
            if active >= settings.RATING_QUEUE_LIMIT:
                raise RatingQueueFull(
                    "Performance rating queue is busy. Try again later."
                )
            connection.execute(
                "INSERT INTO rating_jobs (id, status, pgn, expires) "
                "VALUES (?, ?, ?, ?)",
                (job.id, job.status, pgn, time() + settings.RATING_JOB_TTL_SECONDS),
            )
        return job

    def get(self, job_id: str) -> RatingJob | None:
        """Look up an unexpired result without exposing its input.

        Args:
            job_id: Unguessable identifier returned by submit.

        Returns:
            Public job state, or None for unknown/expired jobs.
        """
        with self._connection() as connection:
            connection.execute(EXPIRE_JOBS_SQL, (time(),))
            row = connection.execute(
                "SELECT id, status, result, error FROM rating_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return RatingJob(
            id=row["id"],
            status=row["status"],
            error=row["error"],
            result=json.loads(row["result"]) if row["result"] else None,
        )

    def claim(self) -> tuple[str, str] | None:
        """Claim the oldest queued game; only the locked worker calls this.

        Args:
            None.

        Returns:
            Job ID and PGN, or None if no game is waiting.
        """
        with self._connection() as connection:
            connection.execute(EXPIRE_JOBS_SQL, (time(),))
            row = connection.execute(
                "SELECT id, pgn FROM rating_jobs WHERE status = 'queued' "
                "ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE rating_jobs SET status = 'running' WHERE id = ?", (row["id"],)
            )
        return row["id"], row["pgn"]

    def finish(
        self,
        job_id: str,
        *,
        result: RatingResult | None = None,
        error: str | None = None,
    ):
        """Persist a terminal state and delete the raw PGN immediately.

        Args:
            job_id: Claimed job identifier.
            result: Validated estimate on success.
            error: User-safe failure description otherwise.

        Returns:
            None.
        """
        with self._connection() as connection:
            connection.execute(
                "UPDATE rating_jobs SET status = ?, pgn = NULL, result = ?, "
                "error = ? WHERE id = ?",
                (
                    "complete" if result else "failed",
                    result.model_dump_json() if result else None,
                    error,
                    job_id,
                ),
            )

    def recover(self):
        """Fail jobs interrupted by the previous worker, removing their inputs.

        Args:
            None.

        Returns:
            None; call only after acquiring the exclusive worker lock.
        """
        with self._connection() as connection:
            connection.execute(
                "UPDATE rating_jobs SET status = 'failed', pgn = NULL, error = ? "
                "WHERE status = 'running'",
                ("Rating worker restarted. Please analyze the game again.",),
            )


class RatingWorker:
    """Reuse a lazily loaded estimator while processing games sequentially."""

    def __init__(self, store: RatingJobStore, estimator_factory=None):
        """Set up the worker without allocating models or engines.

        Args:
            store: Durable queue shared with the web application.
            estimator_factory: Optional injected estimator constructor for tests.

        Returns:
            None.
        """
        self.store = store
        self.estimator_factory = estimator_factory or self._load_estimator
        self.estimator = None

    @staticmethod
    def _load_estimator():
        """Load optional inference dependencies and trusted deployed weights.

        Args:
            None.

        Returns:
            One estimator with explicit model, engine, cache and compatibility paths.
        """
        config = import_module("elo_model.config").InferenceConfig(
            model_directory=settings.RATING_MODEL_DIRECTORY,
            engine_executable=settings.RATING_STOCKFISH_EXECUTABLE,
            cache_directory=settings.RATING_ANALYSIS_CACHE,
            engine_compatibility=settings.RATING_ENGINE_COMPATIBILITY,
        )
        return import_module("elo_model.inference").RatingEstimator(config)

    def process_next(self) -> bool:
        """Analyze one queued game and record a safe terminal state on failure.

        Args:
            None.

        Returns:
            True when a job was processed, otherwise False.
        """
        claimed = self.store.claim()
        if claimed is None:
            return False
        job_id, pgn = claimed
        try:
            if self.estimator is None:
                self.estimator = self.estimator_factory()
            estimate = self.estimator.predict_pgn(pgn)
            result = RatingResult.model_validate(estimate.model_dump(mode="json"))
        except Exception:
            logger.exception("Performance rating job %s failed", job_id)
            self.store.finish(
                job_id,
                error=(
                    "Performance rating unavailable. "
                    "Check the model and engine configuration."
                ),
            )
        else:
            self.store.finish(job_id, result=result)
        return True
