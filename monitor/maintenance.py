"""Planned maintenance windows that suppress alerts without hiding checks.

Inspired by Uptime Kuma's maintenance mode. A window never stops sampling:
the dashboard keeps measuring, but alert delivery is suppressed while the
window is active and the ledger records why.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

MAX_MAINTENANCE_WINDOWS = 20
MAX_MAINTENANCE_SPAN_DAYS = 30.0
MAX_MAINTENANCE_CHECKS = 200
MAX_MAINTENANCE_NAME_LENGTH = 120
MAX_ACTIVE_WINDOWS = 5
MAX_UPCOMING_WINDOWS = 6


class MaintenanceError(ValueError):
    """Raised when a maintenance window is malformed."""


def parse_timestamp(value: object, *, name: str) -> datetime:
    """Parse an ISO-8601 timestamp that must carry an explicit offset."""
    if not isinstance(value, str) or not value.strip():
        raise MaintenanceError(f"{name} must be an ISO-8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MaintenanceError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise MaintenanceError(f"{name} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


@dataclass(frozen=True)
class MaintenanceWindow:
    id: str
    name: str
    starts_at: datetime
    ends_at: datetime
    check_ids: tuple[str, ...] = ()
    suppress_alerts: bool = True

    def covers(self, check_id: str) -> bool:
        return not self.check_ids or check_id in self.check_ids

    def state(self, now: datetime) -> str:
        if now < self.starts_at:
            return "upcoming"
        if now >= self.ends_at:
            return "past"
        return "active"

    def public_dict(self, now: datetime) -> dict[str, Any]:
        state = self.state(now)
        if state == "upcoming":
            remaining_seconds = (self.starts_at - now).total_seconds()
        elif state == "active":
            remaining_seconds = (self.ends_at - now).total_seconds()
        else:
            remaining_seconds = 0.0
        return {
            "id": self.id,
            "name": self.name,
            "starts_at": _iso(self.starts_at),
            "ends_at": _iso(self.ends_at),
            "check_ids": list(self.check_ids),
            "suppress_alerts": self.suppress_alerts,
            "state": state,
            "remaining_seconds": round(max(0.0, remaining_seconds)),
        }

    def rule_dict(self) -> dict[str, Any]:
        """Expose the configured rule without time-dependent state."""
        return {
            "id": self.id,
            "name": self.name,
            "starts_at": _iso(self.starts_at),
            "ends_at": _iso(self.ends_at),
            "check_ids": list(self.check_ids),
            "suppress_alerts": self.suppress_alerts,
        }


def parse_maintenance_windows(raw: object) -> tuple[MaintenanceWindow, ...]:
    """Validate a bounded maintenance list; empty means "no maintenance"."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise MaintenanceError("maintenance_windows must be a list")
    if len(raw) > MAX_MAINTENANCE_WINDOWS:
        raise MaintenanceError(
            f"maintenance_windows must contain at most {MAX_MAINTENANCE_WINDOWS} entries"
        )

    windows: list[MaintenanceWindow] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        label = f"maintenance_windows[{index}]"
        if not isinstance(item, dict):
            raise MaintenanceError(f"{label} must be an object")

        window_id = item.get("id")
        if not isinstance(window_id, str) or not window_id.strip():
            raise MaintenanceError(f"{label}.id must be a non-empty string")
        window_id = window_id.strip()
        if not all(char.isalnum() or char in "-_" for char in window_id):
            raise MaintenanceError(
                f"{label}.id may only contain letters, digits, '-' and '_'"
            )
        if len(window_id) > 64:
            raise MaintenanceError(f"{label}.id must be at most 64 characters")
        if window_id in seen:
            raise MaintenanceError("maintenance window ids must be unique")
        seen.add(window_id)

        name = item.get("name", window_id)
        if not isinstance(name, str):
            raise MaintenanceError(f"{label}.name must be a string")
        name = " ".join(name.split())
        if not name:
            raise MaintenanceError(f"{label}.name must not be empty")
        if len(name) > MAX_MAINTENANCE_NAME_LENGTH:
            raise MaintenanceError(
                f"{label}.name must be at most "
                f"{MAX_MAINTENANCE_NAME_LENGTH} characters"
            )

        starts_at = parse_timestamp(item.get("starts_at"), name=f"{label}.starts_at")
        ends_at = parse_timestamp(item.get("ends_at"), name=f"{label}.ends_at")
        if ends_at <= starts_at:
            raise MaintenanceError(f"{label}.ends_at must be after starts_at")
        span_days = (ends_at - starts_at).total_seconds() / 86400
        if span_days > MAX_MAINTENANCE_SPAN_DAYS:
            raise MaintenanceError(
                f"{label} must span at most {MAX_MAINTENANCE_SPAN_DAYS:g} days"
            )

        raw_checks = item.get("check_ids")
        if raw_checks is None:
            check_ids: tuple[str, ...] = ()
        else:
            if not isinstance(raw_checks, list) or not all(
                isinstance(entry, str) and entry.strip() for entry in raw_checks
            ):
                raise MaintenanceError(
                    f"{label}.check_ids must be a list of non-empty strings"
                )
            if len(raw_checks) > MAX_MAINTENANCE_CHECKS:
                raise MaintenanceError(
                    f"{label}.check_ids must contain at most "
                    f"{MAX_MAINTENANCE_CHECKS} entries"
                )
            check_ids = tuple(dict.fromkeys(entry.strip() for entry in raw_checks))

        suppress_alerts = item.get("suppress_alerts", True)
        if not isinstance(suppress_alerts, bool):
            raise MaintenanceError(f"{label}.suppress_alerts must be a boolean")

        windows.append(
            MaintenanceWindow(
                id=window_id,
                name=name,
                starts_at=starts_at,
                ends_at=ends_at,
                check_ids=check_ids,
                suppress_alerts=suppress_alerts,
            )
        )
    return tuple(windows)


def summarize_maintenance(
    windows: tuple[MaintenanceWindow, ...],
    checks: list[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Report active and upcoming windows plus the checks they cover.

    Only checks present in the current configuration count, so a stale entry
    for a removed check never fabricates coverage.
    """
    reference = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)
    known = {
        check["id"]
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("id"), str)
    }

    active: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    active_check_ids: list[str] = []
    suppressed_alert_checks = 0

    for window in windows:
        state = window.state(reference)
        payload = window.public_dict(reference)
        if state == "active":
            active.append(payload)
            covered = [
                check_id
                for check_id in (window.check_ids or tuple(sorted(known)))
                if check_id in known
            ]
            active_check_ids.extend(
                check_id for check_id in covered if check_id not in active_check_ids
            )
            if window.suppress_alerts:
                suppressed_alert_checks += len(covered)
        elif state == "upcoming":
            upcoming.append(payload)

    active.sort(key=lambda item: item["ends_at"])
    upcoming.sort(key=lambda item: item["starts_at"])
    return {
        "configured": bool(windows),
        "active": active[:MAX_ACTIVE_WINDOWS],
        "upcoming": upcoming[:MAX_UPCOMING_WINDOWS],
        "active_check_ids": active_check_ids,
        "suppressed_alert_checks": suppressed_alert_checks,
    }


def active_window_for(
    windows: tuple[MaintenanceWindow, ...],
    check_id: str,
    *,
    now: datetime,
) -> MaintenanceWindow | None:
    """Return the first active window that covers ``check_id``, if any."""
    reference = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)
    for window in windows:
        if (
            window.suppress_alerts
            and window.state(reference) == "active"
            and window.covers(check_id)
        ):
            return window
    return None


__all__ = [
    "MAX_ACTIVE_WINDOWS",
    "MAX_MAINTENANCE_SPAN_DAYS",
    "MAX_MAINTENANCE_WINDOWS",
    "MAX_UPCOMING_WINDOWS",
    "MaintenanceError",
    "MaintenanceWindow",
    "active_window_for",
    "parse_maintenance_windows",
    "parse_timestamp",
    "summarize_maintenance",
]
