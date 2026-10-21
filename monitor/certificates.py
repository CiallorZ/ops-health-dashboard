"""Bounded certificate expiry calendar built from real TLS check evidence."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

MAX_CERTIFICATE_UPCOMING = 8
MAX_COMMON_NAME_LENGTH = 120

# Certificates that expire beyond this horizon are not "upcoming" yet; keeping
# the window bounded stops every healthy check from filling the calendar.
UPCOMING_WINDOW_DAYS = 90.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: object) -> datetime | None:
    """Accept the Z-suffixed timestamps produced by the TLS check."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_text(value: object, *, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _grade(remaining_days: float, *, warn_days: float, fail_days: float) -> str:
    if remaining_days <= fail_days:
        return "critical"
    if remaining_days <= warn_days:
        return "warning"
    return "healthy"


def summarize_certificates(
    checks: list[dict[str, Any]],
    *,
    tls_warn_days: float,
    tls_fail_days: float,
    limit: int = MAX_CERTIFICATE_UPCOMING,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a bounded certificate calendar derived from the latest snapshot.

    Only checks that actually returned ``expires_at`` / ``remaining_days`` in
    their metrics are included; a failed TLS handshake contributes nothing
    instead of a guessed expiry date.
    """
    reference = now or _utc_now()
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    reference = reference.astimezone(timezone.utc)

    upcoming_limit = max(1, min(int(limit), MAX_CERTIFICATE_UPCOMING))
    warn_days = float(tls_warn_days)
    fail_days = float(tls_fail_days)

    entries: list[dict[str, Any]] = []
    expired = 0
    critical = 0
    warning = 0
    healthy = 0
    nearest_days: float | None = None

    for check in checks:
        if not isinstance(check, dict):
            continue
        metrics = check.get("metrics")
        if not isinstance(metrics, dict):
            continue
        expires_at = _parse_timestamp(metrics.get("expires_at"))
        raw_remaining = metrics.get("remaining_days")
        if expires_at is None and not isinstance(
            raw_remaining, (int, float)
        ):
            continue
        if isinstance(raw_remaining, bool) or not isinstance(
            raw_remaining, (int, float)
        ):
            continue
        remaining_days = float(raw_remaining)
        if not math.isfinite(remaining_days):
            continue
        if expires_at is not None:
            # Recompute from the measured expiry so a stale cached snapshot
            # cannot keep showing a frozen number.
            remaining_days = (expires_at - reference).total_seconds() / 86400
        remaining_days = round(remaining_days, 1)

        grade = _grade(remaining_days, warn_days=warn_days, fail_days=fail_days)
        if remaining_days <= 0:
            expired += 1
        if grade == "critical":
            critical += 1
        elif grade == "warning":
            warning += 1
        else:
            healthy += 1
        if nearest_days is None or remaining_days < nearest_days:
            nearest_days = remaining_days

        entries.append(
            {
                "check_id": _clean_text(check.get("id"), limit=120),
                "name": _clean_text(check.get("name"), limit=120)
                or _clean_text(check.get("id"), limit=120),
                "group": _clean_text(check.get("group"), limit=80) or "未分组",
                "target": _clean_text(check.get("target"), limit=2048),
                "port": check.get("port") if isinstance(check.get("port"), int) else None,
                "expires_at": expires_at.isoformat(timespec="seconds").replace(
                    "+00:00", "Z"
                )
                if expires_at is not None
                else None,
                "remaining_days": remaining_days,
                "common_name": _clean_text(
                    metrics.get("common_name"), limit=MAX_COMMON_NAME_LENGTH
                ),
                "verified": bool(metrics.get("verify_tls", True)),
                "grade": grade,
            }
        )

    entries.sort(key=lambda item: (item["remaining_days"], item["name"]))
    upcoming = [
        entry
        for entry in entries
        if entry["remaining_days"] <= UPCOMING_WINDOW_DAYS
    ][:upcoming_limit]

    return {
        "generated_at": reference.isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "upcoming_window_days": UPCOMING_WINDOW_DAYS,
        "tracked": len(entries),
        "counts": {
            "expired": expired,
            "critical": critical,
            "warning": warning,
            "healthy": healthy,
        },
        "nearest_remaining_days": nearest_days,
        "thresholds": {
            "tls_warn_days": warn_days,
            "tls_fail_days": fail_days,
        },
        "upcoming": upcoming,
    }


__all__ = [
    "MAX_CERTIFICATE_UPCOMING",
    "UPCOMING_WINDOW_DAYS",
    "summarize_certificates",
]
