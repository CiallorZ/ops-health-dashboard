"""Append-only JSONL history with a bounded in-memory window."""

from __future__ import annotations

import json
import threading
from collections import deque
from pathlib import Path
from typing import Any


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

