"""Bounded webhook alert delivery with cooldown and auditable outcomes."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from . import __version__
from .checks import CheckResult, isoformat, utc_now
from .config import ConfigError, NotificationConfig

MAX_ALERT_RECORDS = 80
MAX_PENDING_DELIVERIES = 32
MAX_DETAIL_LENGTH = 160


def _safe_target(value: object) -> str:
    """Keep monitor context while removing URL credentials and parameters."""
    text = "" if value is None else str(value)
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return text
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        return parsed.scheme + "://" + host + parsed.path
    if port:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _event_name(previous: str | None, current: str) -> str:
    if previous is None:
        return "down" if current == "fail" else "status_change"
    if current == "fail":
        return "down"
    if previous == "fail" and current in {"ok", "warn"}:
        return "recovered"
    if current == "warn":
        return "degraded"
    if previous == "warn" and current == "ok":
        return "recovered"
    return "status_change"


def resolve_notification_settings(
    config: NotificationConfig,
    environ: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Resolve optional environment-backed secrets without exposing values."""
    environment = os.environ if environ is None else environ
    webhook_url = config.webhook_url
    if config.webhook_url_env:
        webhook_url = environment.get(config.webhook_url_env)
        if not webhook_url:
            raise ConfigError(
                "notifications.webhook_url_env references an unset environment variable"
            )
    if webhook_url:
        parsed = urlsplit(webhook_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError(
                "resolved notifications webhook must be an absolute HTTP(S) URL"
            )
        if parsed.username or parsed.password:
            raise ConfigError("resolved notifications webhook must not contain credentials")

    signing_secret = None
    if config.signing_secret_env:
        signing_secret = environment.get(config.signing_secret_env)
        if not signing_secret:
            raise ConfigError(
                "notifications.signing_secret_env references an unset environment variable"
            )
        if len(signing_secret) > 512:
            raise ConfigError("webhook signing secret must be at most 512 characters")
    return webhook_url, signing_secret


class AlertStore:
    """Persist the newest bounded delivery ledger as an atomic JSON document."""

    def __init__(self, data_dir: str | Path, max_items: int = MAX_ALERT_RECORDS) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "alerts.json"
        self.max_items = max_items
        self._lock = threading.Lock()
        self._items: list[dict[str, Any]] = []
        self._load()

    @staticmethod
    def _compact(raw: object) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        record_id = raw.get("id")
        if not isinstance(record_id, str) or not record_id:
            return None
        attempts = raw.get("attempts", 0)
        http_status = raw.get("http_status")
        return {
            "id": record_id[:40],
            "created_at": str(raw.get("created_at", ""))[:40],
            "completed_at": (
                str(raw.get("completed_at"))[:40]
                if raw.get("completed_at") is not None
                else None
            ),
            "event": str(raw.get("event", "status_change"))[:32],
            "check_id": str(raw.get("check_id", ""))[:80],
            "check_name": str(raw.get("check_name", ""))[:120],
            "from_status": str(raw.get("from_status", "unknown"))[:16],
            "to_status": str(raw.get("to_status", "unknown"))[:16],
            "status": str(raw.get("status", "queued"))[:16],
            "attempts": attempts if isinstance(attempts, int) and attempts >= 0 else 0,
            "http_status": (
                http_status
                if isinstance(http_status, int) and 100 <= http_status <= 599
                else None
            ),
            "detail": (
                str(raw.get("detail"))[:MAX_DETAIL_LENGTH]
                if raw.get("detail") is not None
                else None
            ),
        }

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, list):
            return
        compacted = [self._compact(item) for item in payload[-self.max_items :]]
        self._items = [item for item in compacted if item is not None]

    def _write_locked(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(self._items, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def upsert(self, record: dict[str, Any]) -> None:
        compacted = self._compact(record)
        if compacted is None:
            return
        with self._lock:
            self._items = [
                item for item in self._items if item["id"] != compacted["id"]
            ]
            self._items.append(compacted)
            self._items = self._items[-self.max_items :]
            try:
                self._write_locked()
            except OSError:
                # A read-only data directory must not break monitoring.
                pass

    def recent(self, limit: int = 12) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), self.max_items))
        with self._lock:
            return [dict(item) for item in reversed(self._items[-bounded:])]


@dataclass(frozen=True)
class _ResolvedDelivery:
    event: str
    created_at: str
    body: bytes
    headers: dict[str, str]
    record: dict[str, Any]


class AlertDispatcher:
    """Queue status-transition webhooks without blocking snapshot requests."""

    def __init__(
        self,
        webhook_url: str,
        *,
        signing_secret: str | None,
        cooldown_seconds: float,
        timeout_seconds: float,
        retry_attempts: int,
        store: AlertStore,
    ) -> None:
        self.webhook_url = webhook_url
        self.signing_secret = signing_secret
        self.cooldown_seconds = cooldown_seconds
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.store = store
        self._lock = threading.Lock()
        self._cooldowns: dict[tuple[str, str | None, str], float] = {}
        self._pending = 0
        self._idle = threading.Event()
        self._idle.set()
        self._futures: set[Future[None]] = set()
        self._closed = False
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="alert-webhook"
        )

    def status(self, *, limit: int = 12) -> dict[str, Any]:
        with self._lock:
            pending = self._pending
        return {
            "configured": True,
            "signed": self.signing_secret is not None,
            "cooldown_seconds": self.cooldown_seconds,
            "timeout_seconds": self.timeout_seconds,
            "retry_attempts": self.retry_attempts,
            "pending": pending,
            "recent": self.store.recent(limit),
        }

    def notify_transition(
        self,
        check: CheckResult,
        previous_status: str | None,
        summary: dict[str, Any],
        *,
        maintenance_name: str | None = None,
    ) -> None:
        event = _event_name(previous_status, check.status)
        now_monotonic = time.monotonic()
        key = (check.id, previous_status, check.status)
        in_maintenance = bool(maintenance_name)
        with self._lock:
            if self._closed:
                return
            last_sent = self._cooldowns.get(key)
            suppress_for_cooldown = (
                last_sent is not None
                and self.cooldown_seconds > 0
                and now_monotonic - last_sent < self.cooldown_seconds
            )
            at_capacity = self._pending >= MAX_PENDING_DELIVERIES
            if not suppress_for_cooldown and not at_capacity and not in_maintenance:
                # A maintenance suppression must not start a cooldown, so the
                # first real transition after the window still gets delivered.
                self._cooldowns[key] = now_monotonic

        created_at = isoformat(utc_now())
        record = {
            "id": uuid.uuid4().hex[:16],
            "created_at": created_at,
            "completed_at": None,
            "event": event,
            "check_id": check.id,
            "check_name": check.name,
            "from_status": previous_status or "unknown",
            "to_status": check.status,
            "status": "queued",
            "attempts": 0,
            "http_status": None,
            "detail": None,
        }
        if suppress_for_cooldown or at_capacity or in_maintenance:
            record["status"] = "suppressed"
            record["completed_at"] = created_at
            record["detail"] = (
                f"maintenance window: {maintenance_name[:80]}"
                if in_maintenance
                else "cooldown window"
                if suppress_for_cooldown
                else "delivery queue is full"
            )
            self.store.upsert(record)
            return

        payload = {
            "schema": "sentinel.alert.v1",
            "event": event,
            "sent_at": created_at,
            "version": __version__,
            "monitor": {
                "id": check.id,
                "name": check.name,
                "type": check.type,
                "target": _safe_target(check.target),
                "group": check.group,
                "domain": check.domain,
                "status": check.status,
                "summary": check.summary,
                "latency_ms": (
                    round(check.latency_ms, 1)
                    if check.latency_ms is not None
                    else None
                ),
                "checked_at": check.checked_at,
            },
            "transition": {
                "from": previous_status or "unknown",
                "to": check.status,
            },
            "summary": {
                "health": summary.get("health"),
                "total": summary.get("total"),
                "ok": summary.get("ok"),
                "warn": summary.get("warn"),
                "fail": summary.get("fail"),
            },
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": f"ops-health-dashboard/{__version__}",
            "X-Sentinel-Event": event,
            "X-Sentinel-Delivery": record["id"],
        }
        if self.signing_secret is not None:
            timestamp = str(int(time.time()))
            signed = timestamp.encode("ascii") + b"." + body
            digest = hmac.new(
                self.signing_secret.encode("utf-8"), signed, hashlib.sha256
            ).hexdigest()
            headers["X-Sentinel-Timestamp"] = timestamp
            headers["X-Sentinel-Signature"] = f"sha256={digest}"

        delivery = _ResolvedDelivery(
            event=event,
            created_at=created_at,
            body=body,
            headers=headers,
            record=record,
        )
        self.store.upsert(record)
        with self._lock:
            self._pending += 1
            self._idle.clear()
            future = self._executor.submit(self._deliver, delivery)
            self._futures.add(future)
            future.add_done_callback(self._delivery_finished)

    def _delivery_finished(self, future: Future[None]) -> None:
        with self._lock:
            self._futures.discard(future)
            self._pending = max(0, self._pending - 1)
            if self._pending == 0:
                self._idle.set()

    def _deliver(self, delivery: _ResolvedDelivery) -> None:
        record = dict(delivery.record)
        final_status = "failed"
        detail = None
        for attempt in range(1, self.retry_attempts + 2):
            record["attempts"] = attempt
            record["status"] = "retrying" if attempt > 1 else "delivering"
            self.store.upsert(record)
            request = urllib.request.Request(
                self.webhook_url,
                data=delivery.body,
                headers=delivery.headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    http_status = response.status
                    response.read(1)
                record["http_status"] = http_status
                if 200 <= http_status <= 299:
                    final_status = "delivered"
                    detail = None
                    break
                detail = f"HTTP {http_status}"
                if 400 <= http_status <= 499:
                    break
            except urllib.error.HTTPError as exc:
                record["http_status"] = exc.code
                detail = f"HTTP {exc.code}"
                exc.close()
                if 400 <= exc.code <= 499:
                    break
            except urllib.error.URLError as exc:
                detail = f"network error: {type(exc.reason).__name__}"
            except (TimeoutError, OSError) as exc:
                detail = f"delivery error: {type(exc).__name__}"
            if attempt <= self.retry_attempts:
                time.sleep(min(0.25 * attempt, 0.5))

        record["status"] = final_status
        record["detail"] = detail[:MAX_DETAIL_LENGTH] if detail else None
        record["completed_at"] = isoformat(utc_now())
        self.store.upsert(record)

    def wait_for_idle(self, timeout: float = 5) -> bool:
        return self._idle.wait(timeout)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            futures = list(self._futures)
        for future in futures:
            future.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)


def create_alert_dispatcher(
    config: NotificationConfig,
    data_dir: str | Path,
) -> AlertDispatcher | None:
    webhook_url, signing_secret = resolve_notification_settings(config)
    if webhook_url is None:
        return None
    return AlertDispatcher(
        webhook_url,
        signing_secret=signing_secret,
        cooldown_seconds=config.cooldown_seconds,
        timeout_seconds=config.timeout_seconds,
        retry_attempts=config.retry_attempts,
        store=AlertStore(data_dir),
    )
