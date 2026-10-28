"""Run the single-concurrency, durable performance-rating worker."""

from importlib import import_module
from threading import Event

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from chess_analyzer.web.rating_jobs import RatingJobStore, RatingWorker


class Command(BaseCommand):
    """Consume rating jobs separately from HTTP requests."""

    help = "Run one rating worker against the shared local SQLite queue."

    def add_arguments(self, parser):
        """Register a one-job mode for operational checks.

        Args:
            parser: Django command argument parser.

        Returns:
            None.
        """
        parser.add_argument(
            "--once", action="store_true", help="Process at most one job."
        )

    def handle(self, *args, **options):
        """Hold an interprocess lock for the worker's entire lifetime.

        Args:
            args: Unused positional command arguments.
            options: Parsed flags including once.

        Returns:
            None; another worker or missing deployment settings raises CommandError.
        """
        if (
            not settings.RATING_MODEL_DIRECTORY
            or not settings.RATING_STOCKFISH_EXECUTABLE
        ):
            raise CommandError(
                "Set RATING_MODEL_DIRECTORY and RATING_STOCKFISH_EXECUTABLE."
            )
        try:
            filelock = import_module("filelock")
        except ImportError as error:
            raise CommandError("Install the application's [rating] extra.") from error
        store = RatingJobStore()
        try:
            with filelock.FileLock(str(store.path) + ".worker.lock", timeout=0):
                store.recover()
                worker = RatingWorker(store)
                stopped = Event()
                try:
                    while True:
                        processed = worker.process_next()
                        if options["once"]:
                            break
                        if not processed:
                            stopped.wait(settings.RATING_POLL_SECONDS)
                except KeyboardInterrupt:
                    self.stdout.write("Rating worker stopped.")
        except filelock.Timeout as error:
            raise CommandError("A rating worker already owns this queue.") from error
