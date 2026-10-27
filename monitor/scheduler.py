"""Background monitor loop that keeps sampling without an open browser."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from .runner import CheckRunnerService


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


class BackgroundMonitor:
    """Run one bounded snapshot per interval and expose its health state."""

    def __init__(
        self,
        runner: CheckRunnerService,
        interval_seconds: float,
    ) -> None:
        self.runner = runner
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running = False
        self._last_run_at: str | None = None
        self._last_completed_at: str | None = None
        self._next_run_at: str | None = None
        self._last_run_id: str | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._loop,
                name="sentinel-monitor",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join()
        with self._lock:
            self._thread = None
            self._running = False
            self._next_run_at = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.interval_seconds)

    def run_once(self) -> dict[str, Any] | None:
        with self._lock:
            self._last_run_at = _iso_now()
        try:
            snapshot = self.runner.get_snapshot(force=True, history_limit=40)
        except Exception as exc:  # Keep the scheduler alive after a failed run.
            with self._lock:
                self._last_error = type(exc).__name__
                self._last_completed_at = _iso_now()
                self._next_run_at = None
            return None

        with self._lock:
            self._last_completed_at = _iso_now()
            self._last_run_id = snapshot.get("run_id")
            self._last_error = None
            next_epoch = time.time() + self.interval_seconds
            self._next_run_at = (
                datetime.fromtimestamp(next_epoch, tz=timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            )
        return snapshot

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._running and (
                self._thread is not None and self._thread.is_alive()
            )
            return {
                "running": running,
                "interval_seconds": self.interval_seconds,
                "last_run_at": self._last_run_at,
                "last_completed_at": self._last_completed_at,
                "next_run_at": self._next_run_at if running else None,
                "last_run_id": self._last_run_id,
                "last_error": self._last_error,
            }
