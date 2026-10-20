"""Append-only JSONL history with a bounded in-memory window."""

from __future__ import annotations

import json
import math
import threading
from collections import deque
from pathlib import Path
from typing import Any

CHECK_STATUSES = frozenset({"ok", "warn", "fail"})
MAX_HISTORY_CHECKS_PER_RUN = 200
MAX_TRANSITION_EVENTS = 8


def _latency(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    latency = float(value)
    if not math.isfinite(latency) or latency < 0:
        return None
    return round(latency, 1)


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


class HistoryStore:
    def __init__(self, data_dir: str | Path, max_memory: int = 240) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "history.jsonl"
        self.max_memory = max_memory
        self._lock = threading.Lock()
        self._items: deque[dict[str, Any]] = deque(maxlen=max_memory)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                lines = deque(handle, maxlen=self.max_memory)
        except OSError:
            return
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                self._items.append(item)

    def append(self, item: dict[str, Any]) -> None:
        with self._lock:
            self._items.append(item)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            except OSError:
                # History is useful, but a read-only disk must not break checks.
                pass

    def recent(self, limit: int = 40) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), self.max_memory))
        with self._lock:
            return list(self._items)[-bounded:]

