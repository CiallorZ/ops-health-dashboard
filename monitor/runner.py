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
from .certificates import summarize_certificates
from .config import CheckConfig, DashboardConfig, Thresholds
from .history import (
    HistoryStore,
    MAX_TREND_ITEMS,
    MAX_TREND_DAYS,
    summarize_check_history,
    summarize_history_trends,
)
from .maintenance import active_window_for, summarize_maintenance

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
                            "domain": result.domain,
                            "status": result.status,
                            "latency_ms": (
                                round(result.latency_ms, 1)
                                if result.latency_ms is not None
                                else None
                            ),
                            **(
                                {"assertions": result.assertions}
                                if result.assertions
                                else {}
                            ),
                            **(
                                {"metrics": {name: result.metrics[name] for name in (
                                    "total_bytes", "used_bytes", "free_bytes", "free_percent"
                                ) if name in result.metrics}}
                                if result.type == "disk" else {}
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

    def get_certificates(self) -> dict[str, Any]:
        """Return a bounded certificate calendar from the latest TLS evidence."""
        snapshot = self._cached if self._cached is not None else self.get_snapshot()
        return summarize_certificates(
            snapshot.get("checks", []),
            tls_warn_days=self.config.thresholds.tls_warn_days,
            tls_fail_days=self.config.thresholds.tls_fail_days,
        )

    def get_maintenance(self) -> dict[str, Any]:
        """Return active and upcoming windows from the current configuration."""
        snapshot = self._cached if self._cached is not None else self.get_snapshot()
        return summarize_maintenance(
            self.config.maintenance_windows,
            snapshot.get("checks", []),
            now=_utc_now(),
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
                window = active_window_for(
                    self.config.maintenance_windows,
                    result.id,
                    now=_utc_now(),
                )
                self.alert_dispatcher.notify_transition(
                    result,
                    previous,
                    summary,
                    maintenance_name=window.name if window is not None else None,
                )
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

    def metrics_payload(self) -> str:
        lines = []
        checks = (self._cached or {}).get("checks", [])
        for check in checks:
            # The label carries the real monitoring domain (v0.12 contract),
            # not the free-text business group, so dashboards can filter by
            # domain without changing existing metric names.
            domain = _label(str(check.get("domain", "network")))
            check_id = _label(str(check.get("id", "")))
            labels = 'domain="' + domain + '",id="' + check_id + '"'
            status = str(check.get("status", "unknown"))
            up = 1 if status == "ok" else 0
            lines.append("sentinel_check_up{" + labels + "} " + str(up))
            for state in ("ok", "warn", "fail", "unknown"):
                value = 1 if status == state else 0
                lines.append('sentinel_check_status{' + labels + ',status="' + state + '"} ' + str(value))
            latency = check.get("latency_ms")
            if latency is not None:
                lines.append("sentinel_check_latency_ms{" + labels + "} " + str(latency))
            if check.get("type") == "disk":
                metrics = check.get("metrics", {})
                for name in ("total_bytes", "used_bytes", "free_bytes", "free_percent"):
                    value = metrics.get(name)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        lines.append("sentinel_disk_" + name + "{" + labels + "} " + str(value))
        stats = self.history.stats()
        lines.append("sentinel_history_bytes " + str(stats["current_bytes"]))
        lines.append("sentinel_history_max_bytes " + str(stats["max_file_bytes"]))
        lines.append("sentinel_history_loaded_lines " + str(stats["loaded_lines"]))
        lines.append("sentinel_history_max_load_lines " + str(stats["max_load_lines"]))
        lines.append("sentinel_history_truncated " + ("1" if stats["truncated"] else "0"))
        return "\n".join(lines) + "\n"

    def _execute(self, checks: list[CheckConfig]) -> list[CheckResult]:
        if not checks:
            return []
        # One pool per domain so a slow domain cannot starve a fast one. Each
        # domain stays inside its own declared budget and the process-wide
        # ``max_workers`` cap still applies to the largest single domain.
        by_domain: dict[str, list[CheckConfig]] = {}
        for check in checks:
            by_domain.setdefault(check.domain, []).append(check)

        results: dict[str, CheckResult] = {}
        executors = {
            domain: ThreadPoolExecutor(
                max_workers=max(
                    1,
                    min(
                        self.config.workers_for_domain(domain),
                        self.max_workers,
                        len(domain_checks),
                    ),
                ),
                thread_name_prefix=f"health-{domain}",
            )
            for domain, domain_checks in by_domain.items()
        }
        try:
            futures = {
                executor.submit(self._run_with_retries, check): check
                for domain, executor in executors.items()
                for check in by_domain[domain]
            }
            for future, check in futures.items():
                results[check.id] = future.result()
        finally:
            for executor in executors.values():
                executor.shutdown(wait=True)
        return [results[check.id] for check in checks]

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
        counts = {"ok": 0, "warn": 0, "fail": 0, "unknown": 0}
        for result in results:
            if result.status in counts:
                counts[result.status] += 1
        if counts["fail"]:
            health = "critical"
        elif counts["warn"]:
            health = "degraded"
        elif counts["unknown"]:
            health = "unknown"
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
            "unknown": counts["unknown"],
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


def _label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
