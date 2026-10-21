"""Run all configured checks, cache snapshots, and record summaries."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from .alerts import AlertDispatcher
from .checks import CheckResult, run_check
from .config import CheckConfig, DashboardConfig, Thresholds
from .history import (
    HistoryStore,
    MAX_TREND_ITEMS,
    MAX_TREND_DAYS,
    summarize_check_history,
    summarize_history_trends,
)

CheckRunner = Callable[[CheckConfig, Thresholds], CheckResult]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class CheckRunnerService:
    def __init__(
        self,
        config: DashboardConfig,
        history: HistoryStore,
        *,
        cache_seconds: float = 8.0,
        max_workers: int = 8,
        check_runner: CheckRunner = run_check,
        alert_dispatcher: AlertDispatcher | None = None,
    ) -> None:
        self.config = config
        self.history = history
        self.cache_seconds = cache_seconds
        self.max_workers = max_workers
        self.check_runner = check_runner
        self.alert_dispatcher = alert_dispatcher
        self._lock = threading.Lock()
        self._cached: dict | None = None
        self._cached_at = 0.0
        self._last_statuses: dict[str, str] = {}

    def get_snapshot(
        self,
        *,
        force: bool = False,
        history_limit: int = 40,
        trend_days: int | None = None,
    ) -> dict:
        request_started = time.monotonic()
        if not force and self._cached is not None:
            age = request_started - self._cached_at
            if age < self.cache_seconds:
                return self._with_history(self._cached, history_limit, trend_days)

        with self._lock:
            if self._cached is not None:
                age = time.monotonic() - self._cached_at
                # A snapshot created while this request waited on the lock is
                # already fresh enough to satisfy it, even a forced refresh.
                if self._cached_at >= request_started:
                    return self._with_history(self._cached, history_limit, trend_days)
                if not force and age < self.cache_seconds:
                    return self._with_history(self._cached, history_limit, trend_days)

            started = time.perf_counter()
            run_at = _iso(_utc_now())
            enabled = [check for check in self.config.checks if check.enabled]
            results = self._execute(enabled)
            duration_ms = (time.perf_counter() - started) * 1000
            summary = self._summarize(results)
            self._dispatch_transitions(results, summary)
            snapshot = {
                "run_id": uuid.uuid4().hex[:12],
                "generated_at": run_at,
                "duration_ms": round(duration_ms, 1),
                "summary": summary,
                "checks": [result.to_dict() for result in results],
            }
            self._cached = snapshot
            self._cached_at = time.monotonic()
            self.history.append(
                {
                    "run_id": snapshot["run_id"],
                    "generated_at": run_at,
                    "duration_ms": snapshot["duration_ms"],
                    **summary,
                    "checks": [
                        {
                            "id": result.id,
                            "status": result.status,
                            "latency_ms": (
                                round(result.latency_ms, 1)
                                if result.latency_ms is not None
                                else None
                            ),
                        }
                        for result in results
                    ],
                }
            )
            return self._with_history(snapshot, history_limit, trend_days)

    def get_trends(self, *, days: int = 7) -> dict[str, Any]:
        """Return bounded daily rollups without triggering another check run."""
        bounded_days = max(1, min(int(days), MAX_TREND_DAYS))
        snapshot = self._cached if self._cached is not None else self.get_snapshot()
        history = self.history.recent(MAX_TREND_ITEMS)
        return summarize_history_trends(
            history,
            snapshot.get("checks", []),
            days=bounded_days,
        )

    def _dispatch_transitions(
        self, results: list[CheckResult], summary: dict[str, Any]
    ) -> None:
        if self.alert_dispatcher is None:
            self._last_statuses.update(
                {result.id: result.status for result in results}
            )
            return
        for result in results:
            previous = self._last_statuses.get(result.id)
            changed = previous is not None and previous != result.status
            first_failure = previous is None and result.status == "fail"
            if changed or first_failure:
                self.alert_dispatcher.notify_transition(result, previous, summary)
            self._last_statuses[result.id] = result.status

    def alert_status(self, *, limit: int = 12) -> dict[str, Any]:
        if self.alert_dispatcher is None:
            return {
                "configured": False,
                "signed": False,
                "pending": 0,
                "recent": [],
            }
        return self.alert_dispatcher.status(limit=limit)

    def _execute(self, checks: list[CheckConfig]) -> list[CheckResult]:
        if not checks:
            return []
        workers = max(1, min(self.max_workers, len(checks)))
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="health-check"
        ) as executor:
            futures = [
                executor.submit(self._run_with_retries, check)
                for check in checks
            ]
            return [future.result() for future in futures]

    def _run_with_retries(self, check: CheckConfig) -> CheckResult:
        """Retry only a completed failed result, preserving the final evidence."""
        attempts = 0
        result: CheckResult | None = None
        while attempts <= check.retry_attempts:
            attempts += 1
            result = self.check_runner(check, self.config.thresholds)
            if result.status != "fail":
                break
        assert result is not None
        result.metrics = {
            **result.metrics,
            "attempts": attempts,
            "recovered_after_retry": attempts > 1 and result.status != "fail",
        }
        return result

    @staticmethod
    def _summarize(results: list[CheckResult]) -> dict:
        counts = {"ok": 0, "warn": 0, "fail": 0}
        for result in results:
            if result.status in counts:
                counts[result.status] += 1
        if counts["fail"]:
            health = "critical"
        elif counts["warn"]:
            health = "degraded"
        elif results:
            health = "healthy"
        else:
            health = "empty"
        return {
            "health": health,
            "total": len(results),
            "ok": counts["ok"],
            "warn": counts["warn"],
            "fail": counts["fail"],
        }

    def _with_history(
        self,
        snapshot: dict,
        history_limit: int,
        trend_days: int | None = None,
    ) -> dict:
        history = self.history.recent(history_limit)
        payload = {
            **snapshot,
            "history": history,
            "check_history": summarize_check_history(
                history,
                snapshot.get("checks", []),
                limit=history_limit,
            ),
        }
        if trend_days is not None:
            payload["trends"] = summarize_history_trends(
                self.history.recent(MAX_TREND_ITEMS),
                snapshot.get("checks", []),
                days=trend_days,
            )
        return payload

