"""Append-only JSONL history with a bounded in-memory window."""

from __future__ import annotations

import bisect
import json
import math
import threading
from collections import deque
from datetime import date
from pathlib import Path
from typing import Any

CHECK_STATUSES = frozenset({"ok", "warn", "fail"})
MAX_HISTORY_CHECKS_PER_RUN = 200
MAX_TRANSITION_EVENTS = 8
MAX_TREND_DAYS = 30
MAX_TREND_ITEMS = 2000

# On-disk bounds. A single history file may not grow past ``max_file_bytes``;
# older runs are rotated into a fixed number of archives so the total
# footprint stays bounded even on a host that never cleans ``data/``.
DEFAULT_MAX_HISTORY_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_FILES = 2
DEFAULT_MAX_LOAD_LINES = 5000
DEFAULT_MAX_MEMORY_ITEMS = 240

LATENCY_BUCKETS: tuple[float, ...] = (
    10.0,
    25.0,
    50.0,
    100.0,
    200.0,
    300.0,
    400.0,
    600.0,
    800.0,
    1000.0,
    1500.0,
    2000.0,
)


def _latency(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    latency = float(value)
    if not math.isfinite(latency) or latency < 0:
        return None
    return round(latency, 1)


def _percentile(histogram: list[int], total: int, fraction: float) -> float | None:
    """Read pNN from fixed latency buckets.

    A histogram keeps the persisted trend payload bounded; the percentile is
    interpolated inside the bucket that contains the requested rank, so the
    result is approximated but always derived from real samples.
    """
    if total <= 0:
        return None
    bucket_count = len(LATENCY_BUCKETS) + 1
    target_rank = min(total - 1, max(0, math.ceil(fraction * total) - 1))
    seen = 0
    index = 0
    while index < bucket_count - 1:
        seen += histogram[index]
        if seen > target_rank:
            break
        index += 1
    previous = seen - histogram[index]
    bucket_start = 0.0 if index == 0 else float(LATENCY_BUCKETS[index - 1])
    if index >= len(LATENCY_BUCKETS):
        return round(bucket_start, 1)

    bucket_end = float(LATENCY_BUCKETS[index])
    offset = max(1, target_rank - previous + 1)
    ratio = offset / histogram[index] if histogram[index] else 0.5
    return round(bucket_start + (bucket_end - bucket_start) * min(1.0, ratio), 1)


def _day_key(value: object) -> str | None:
    """Return the UTC date of a run timestamp, or None when it is unreadable.

    The prefix is parsed as a real calendar date so impossible values such as
    ``2026-13-45`` never become trend days.
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    day = value[:10]
    try:
        return date.fromisoformat(day).isoformat()
    except ValueError:
        return None


def _bucket_index(latency_ms: float) -> int:
    return bisect.bisect_left(LATENCY_BUCKETS, latency_ms)


def _daily_entry() -> dict[str, Any]:
    return {
        "samples": 0,
        "ok": 0,
        "warn": 0,
        "fail": 0,
        "histogram": [0] * (len(LATENCY_BUCKETS) + 1),
        "latency_samples": 0,
    }


def _finalize_daily(entry: dict[str, Any]) -> dict[str, Any]:
    samples = entry.pop("samples")
    histogram = entry.pop("histogram")
    latency_samples = entry.pop("latency_samples")
    entry["samples"] = samples
    entry["availability_percent"] = (
        round((entry["ok"] + entry["warn"]) / samples * 100, 1) if samples else None
    )
    entry["p50_latency_ms"] = _percentile(histogram, latency_samples, 0.5)
    entry["p95_latency_ms"] = _percentile(histogram, latency_samples, 0.95)
    entry["latency_samples"] = latency_samples
    return entry


def _finalize_check(
    check_id: str,
    days: dict[str, dict[str, Any]],
    *,
    day_limit: int,
) -> dict[str, Any] | None:
    if not days:
        return None
    ordered = sorted(days, reverse=True)[:day_limit]
    daily = {day: _finalize_daily(days[day]) for day in ordered}
    return {
        "check_id": check_id,
        "days_with_data": len(daily),
        "daily": daily,
        "totals": {
            "samples": sum(item["samples"] for item in daily.values()),
            "ok": sum(item["ok"] for item in daily.values()),
            "warn": sum(item["warn"] for item in daily.values()),
            "fail": sum(item["fail"] for item in daily.values()),
        },
    }


def summarize_check_history(
    history: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    *,
    limit: int = 40,
) -> dict[str, Any]:
    """Build bounded per-check availability and transition evidence.

    Older history rows do not contain ``checks``. They remain valid run-level
    history but contribute no fabricated per-check samples.
    """
    bounded = max(1, min(int(limit), 200))
    current = {
        check["id"]: check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("id"), str)
    }
    samples_by_id: dict[str, list[dict[str, Any]]] = {
        check_id: [] for check_id in current
    }
    previous_status: dict[str, str] = {}
    latest_change: dict[str, dict[str, str]] = {}
    events: list[dict[str, Any]] = []

    for item in history[-bounded:]:
        if not isinstance(item, dict):
            continue
        generated_at = item.get("generated_at")
        if not isinstance(generated_at, str):
            generated_at = ""
        raw_checks = item.get("checks")
        if not isinstance(raw_checks, list):
            continue

        seen_in_run: set[str] = set()
        for raw_check in raw_checks[:MAX_HISTORY_CHECKS_PER_RUN]:
            if not isinstance(raw_check, dict):
                continue
            check_id = raw_check.get("id")
            status = raw_check.get("status")
            if (
                not isinstance(check_id, str)
                or check_id not in current
                or check_id in seen_in_run
                or status not in CHECK_STATUSES
            ):
                continue
            seen_in_run.add(check_id)
            sample = {
                "status": status,
                "latency_ms": _latency(raw_check.get("latency_ms")),
                "at": generated_at,
            }
            samples_by_id[check_id].append(sample)

            previous = previous_status.get(check_id)
            if previous is not None and previous != status:
                change = {"from": previous, "to": status, "at": generated_at}
                latest_change[check_id] = change
                meta = current[check_id]
                events.append(
                    {
                        "check_id": check_id,
                        "name": meta.get("name", check_id),
                        "group": meta.get("group", "未分组"),
                        **change,
                    }
                )
            previous_status[check_id] = status

    summaries: dict[str, dict[str, Any]] = {}
    for check_id, samples in samples_by_id.items():
        if not samples:
            continue
        counts = {"ok": 0, "warn": 0, "fail": 0}
        latencies: list[float] = []
        for sample in samples:
            counts[sample["status"]] += 1
            if sample["latency_ms"] is not None:
                latencies.append(sample["latency_ms"])
        sample_count = len(samples)
        summaries[check_id] = {
            "window": bounded,
            "samples": sample_count,
            "availability_percent": round(
                (counts["ok"] + counts["warn"]) / sample_count * 100,
                1,
            ),
            "average_latency_ms": (
                round(sum(latencies) / len(latencies), 1) if latencies else None
            ),
            "counts": counts,
            "heartbeats": samples,
            "last_change": latest_change.get(check_id),
        }

    return {
        "window": bounded,
        "checks": summaries,
        "events": list(reversed(events))[:MAX_TRANSITION_EVENTS],
    }


def summarize_history_trends(
    history: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    *,
    days: int = 7,
) -> dict[str, Any]:
    """Build bounded daily availability and latency percentiles from real runs.

    Only days that contain samples are returned. Missing days are never filled
    with assumed values; ``days`` only bounds how many recent days are kept.
    """
    day_limit = max(1, min(int(days), MAX_TREND_DAYS))
    current = {
        check["id"]: check
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("id"), str)
    }

    per_check: dict[str, dict[str, dict[str, Any]]] = {
        check_id: {} for check_id in current
    }
    overall: dict[str, dict[str, Any]] = {}

    for item in history[-MAX_TREND_ITEMS:]:
        if not isinstance(item, dict):
            continue
        day = _day_key(item.get("generated_at"))
        raw_checks = item.get("checks")
        if day is None or not isinstance(raw_checks, list):
            continue

        seen_in_run: set[str] = set()
        used_samples: list[tuple[dict[str, Any], str, float | None]] = []
        for raw_check in raw_checks[:MAX_HISTORY_CHECKS_PER_RUN]:
            if not isinstance(raw_check, dict):
                continue
            check_id = raw_check.get("id")
            status = raw_check.get("status")
            if (
                not isinstance(check_id, str)
                or check_id not in current
                or check_id in seen_in_run
                or status not in CHECK_STATUSES
            ):
                continue
            seen_in_run.add(check_id)
            latency = _latency(raw_check.get("latency_ms"))
            used_samples.append((per_check[check_id], status, latency))

        if not used_samples:
            # A run without valid per-check samples must not create a trend day.
            continue

        overall.setdefault(day, _daily_entry())
        for check_days, status, latency in used_samples:
            check_entry = check_days.setdefault(day, _daily_entry())
            overall_entry = overall[day]
            for entry in (check_entry, overall_entry):
                entry["samples"] += 1
                entry[status] += 1
                if latency is not None:
                    entry["histogram"][_bucket_index(latency)] += 1
                    entry["latency_samples"] += 1

    check_summaries: dict[str, dict[str, Any]] = {}
    for check_id, check_days in per_check.items():
        summary = _finalize_check(check_id, check_days, day_limit=day_limit)
        if summary is not None:
            check_summaries[check_id] = summary

    ordered_days = sorted(overall, reverse=True)[:day_limit]
    daily_totals = {day: _finalize_daily(overall[day]) for day in ordered_days}
    return {
        "days": day_limit,
        "days_with_data": len(daily_totals),
        "generated_from_utc_days": True,
        "daily": daily_totals,
        "checks": check_summaries,
        "latency_buckets_ms": list(LATENCY_BUCKETS),
    }


class HistoryStore:
    """Append-only JSONL history with bounded memory, disk size, and archives.

    Rotation only ever moves files inside ``data_dir``. When a write would
    exceed the byte budget, the current file becomes ``history.1.jsonl`` and
    the previous archives shift down; anything past ``max_archive_files`` is
    removed. The newest runs are therefore always retained.
    """

    def __init__(
        self,
        data_dir: str | Path,
        max_memory: int = DEFAULT_MAX_MEMORY_ITEMS,
        *,
        max_file_bytes: int = DEFAULT_MAX_HISTORY_BYTES,
        max_archive_files: int = DEFAULT_MAX_ARCHIVE_FILES,
        max_load_lines: int = DEFAULT_MAX_LOAD_LINES,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "history.jsonl"
        self.max_memory = max(1, int(max_memory))
        self.max_file_bytes = max(1024, int(max_file_bytes))
        self.max_archive_files = max(0, int(max_archive_files))
        self.max_load_lines = max(1, int(max_load_lines))
        self._lock = threading.Lock()
        self._items: deque[dict[str, Any]] = deque(maxlen=self.max_memory)
        self._truncated = False
        self._prepare_files()
        self._load()

    # ------------------------------------------------------------------ paths
    def _archive_path(self, index: int) -> Path:
        return self.data_dir / f"history.{index}.jsonl"

    def _archive_paths(self) -> list[Path]:
        """Return existing archives from newest (1) to oldest."""
        paths: list[Path] = []
        for index in range(1, self.max_archive_files + 1):
            path = self._archive_path(index)
            if path.is_file():
                paths.append(path)
        return paths

    def _size(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    # ------------------------------------------------------------------- load
    def _tail_lines(self, path: Path) -> list[str]:
        """Read at most ``max_file_bytes`` from the end of one history file."""
        try:
            size = self._size(path)
            if not size:
                return []
            with path.open("rb") as handle:
                if size > self.max_file_bytes:
                    # Drop the first partial line so JSON stays parseable.
                    handle.seek(size - self.max_file_bytes)
                    handle.readline()
                payload = handle.read(self.max_file_bytes)
        except OSError:
            return []
        return payload.decode("utf-8", errors="replace").splitlines()

    def _load(self) -> None:
        """Load newest-bounded history across the current file and archives."""
        files = list(reversed(self._archive_paths())) + [self.path]
        retained: deque[str] = deque(maxlen=self.max_load_lines)
        total_lines = 0
        for path in files:
            if not path.is_file():
                continue
            if self._size(path) > self.max_file_bytes:
                # Part of the file is unreadable by design; say so instead of
                # presenting the surviving tail as complete history.
                self._truncated = True
            lines = self._tail_lines(path)
            total_lines += len(lines)
            retained.extend(lines)
        if total_lines > self.max_load_lines:
            self._truncated = True

        for line in retained:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                self._items.append(item)

    # --------------------------------------------------------------- rotation
    def _remove(self, path: Path) -> bool:
        """Delete a history file only when it resolves inside ``data_dir``."""
        try:
            root = self.data_dir.resolve()
            resolved = path.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            return False
        try:
            resolved.unlink()
            return True
        except OSError:
            return False

    def _rotate_locked(self) -> bool:
        """Move the current file into the bounded archive chain."""
        if not self.path.is_file() or self._size(self.path) == 0:
            return False
        if self.max_archive_files == 0:
            self._truncated = True
            return self._remove(self.path)
        try:
            # Dropping the oldest archive is real data loss, so report it.
            if self._remove(self._archive_path(self.max_archive_files)):
                self._truncated = True
            for index in range(self.max_archive_files - 1, 0, -1):
                older = self._archive_path(index)
                if older.is_file():
                    older.replace(self._archive_path(index + 1))
            self.path.replace(self._archive_path(1))
        except OSError:
            return False
        return True

    def _compact_locked(self, path: Path) -> None:
        """Rewrite an oversized file down to its newest complete lines."""
        if self._size(path) <= self.max_file_bytes:
            return
        self._truncated = True
        lines = self._tail_lines(path)
        if not lines:
            self._remove(path)
            return
        # ``_tail_lines`` can end on a partial record and re-encoding may shift
        # the byte count, so trim from the front until the rewrite really fits.
        while lines:
            payload = ("\n".join(lines) + "\n").encode("utf-8")
            if len(payload) <= self.max_file_bytes:
                break
            lines.pop(0)
        if not lines:
            self._remove(path)
            return
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        except OSError:
            try:
                temporary.unlink()
            except OSError:
                pass

    def _prepare_files(self) -> None:
        """Bound every existing file before anything is loaded or appended."""
        with self._lock:
            self._compact_locked(self.path)
            for path in self._archive_paths():
                self._compact_locked(path)
            # A file that was already at the limit becomes archive #1 so the
            # next run starts from an empty current file.
            if self._size(self.path) >= self.max_file_bytes:
                self._rotate_locked()

    # ------------------------------------------------------------------ write
    def append(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(item)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            payload = (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8")
            # Rotate before writing so a completed file never sits above the
            # cap waiting for the next run to notice.
            if (
                self._size(self.path) > 0
                and self._size(self.path) + len(payload) > self.max_file_bytes
            ):
                self._rotate_locked()
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(payload.decode("utf-8"))
            except OSError:
                # History is useful, but a read-only disk must not break checks.
                return
            if self._size(self.path) > self.max_file_bytes:
                # A single oversized record is trimmed to its newest lines.
                self._compact_locked(self.path)
            elif self._size(self.path) >= self.max_file_bytes:
                self._rotate_locked()

    def recent(self, limit: int = 40) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), self.max_memory))
        with self._lock:
            return list(self._items)[-bounded:]

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict[str, Any]:
        """Report the real on-disk footprint without touching any file."""
        with self._lock:
            current_bytes = self._size(self.path)
            archives = [
                {"name": path.name, "bytes": self._size(path)}
                for path in self._archive_paths()
            ]
            max_total = self.max_file_bytes * (1 + self.max_archive_files)
            total = current_bytes + sum(item["bytes"] for item in archives)
            payload = {
                "current_bytes": current_bytes,
                "max_file_bytes": self.max_file_bytes,
                "archives": archives,
                "max_archive_files": self.max_archive_files,
                "total_bytes": total,
                "max_total_bytes": max_total,
                "loaded_lines": len(self._items),
                "max_load_lines": self.max_load_lines,
                "truncated": self._truncated,
            }
            return payload

