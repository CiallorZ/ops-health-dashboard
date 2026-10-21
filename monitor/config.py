"""Load and validate the dashboard check configuration."""

from __future__ import annotations

import json
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .maintenance import MaintenanceError, MaintenanceWindow, parse_maintenance_windows

SUPPORTED_TYPES = {"http", "tcp", "tls", "ping"}
MAX_CHECKS = 200
MAX_NAME_LENGTH = 120
MAX_TARGET_LENGTH = 2048
MAX_TAGS = 12
MAX_TAG_LENGTH = 40
MAX_WEBHOOK_URL_LENGTH = 2048
HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigError(ValueError):
    """Raised when checks.json is malformed or unsafe to execute."""


@dataclass(frozen=True)
class Thresholds:
    latency_warn_ms: float = 800
    latency_fail_ms: float = 2500
    tls_warn_days: float = 30
    tls_fail_days: float = 7

    def __post_init__(self) -> None:
        if self.latency_warn_ms <= 0 or self.latency_fail_ms <= 0:
            raise ConfigError("latency thresholds must be positive")
        if self.latency_warn_ms >= self.latency_fail_ms:
            raise ConfigError("latency_warn_ms must be lower than latency_fail_ms")
        if self.tls_warn_days <= 0 or self.tls_fail_days <= 0:
            raise ConfigError("TLS thresholds must be positive")
        if self.tls_fail_days >= self.tls_warn_days:
            raise ConfigError("tls_fail_days must be lower than tls_warn_days")


@dataclass(frozen=True)
class NotificationConfig:
    webhook_url: str | None = None
    webhook_url_env: str | None = None
    signing_secret_env: str | None = None
    cooldown_seconds: float = 300
    timeout_seconds: float = 4
    retry_attempts: int = 1

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url or self.webhook_url_env)

    def public_dict(self) -> dict[str, Any]:
        """Expose delivery policy without revealing a webhook endpoint."""
        return {
            "configured": self.configured,
            "webhook_source": (
                "direct"
                if self.webhook_url
                else "environment"
                if self.webhook_url_env
                else None
            ),
            "webhook_url_env": self.webhook_url_env,
            "signing_secret_env": self.signing_secret_env,
            "cooldown_seconds": self.cooldown_seconds,
            "timeout_seconds": self.timeout_seconds,
            "retry_attempts": self.retry_attempts,
        }


@dataclass(frozen=True)
class CheckConfig:
    id: str
    name: str
    type: str
    target: str
    enabled: bool = True
    port: int | None = None
    expected_status: tuple[int, ...] = (200,)
    timeout_seconds: float = 5.0
    retry_attempts: int = 0
    verify_tls: bool = True
    group: str = "未分组"
    tags: tuple[str, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        port = self.port
        if port is None and self.type == "tls":
            port = 443
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "target": self.target,
            "enabled": self.enabled,
            "port": port,
            "expected_status": list(self.expected_status),
            "timeout_seconds": self.timeout_seconds,
            "retry_attempts": self.retry_attempts,
            "verify_tls": self.verify_tls,
            "group": self.group,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class DashboardConfig:
    version: int
    thresholds: Thresholds
    checks: tuple[CheckConfig, ...]
    monitor_interval_seconds: float = 60
    notifications: NotificationConfig = NotificationConfig()
    maintenance_windows: tuple[MaintenanceWindow, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "thresholds": {
                "latency_warn_ms": self.thresholds.latency_warn_ms,
                "latency_fail_ms": self.thresholds.latency_fail_ms,
                "tls_warn_days": self.thresholds.tls_warn_days,
                "tls_fail_days": self.thresholds.tls_fail_days,
            },
            "monitor_interval_seconds": self.monitor_interval_seconds,
            "notifications": self.notifications.public_dict(),
            "maintenance_windows": [
                window.rule_dict() for window in self.maintenance_windows
            ],
            "checks": [check.public_dict() for check in self.checks],
        }


def _number(
    value: Any,
    *,
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number")
    number = float(value)
    if not minimum <= number <= maximum:
        raise ConfigError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


def _port(value: Any, *, name: str, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer")
    if not 1 <= value <= 65535:
        raise ConfigError(f"{name} must be between 1 and 65535")
    return value


def _retry_attempts(value: Any, *, name: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} must be an integer")
    if not 0 <= value <= 2:
        raise ConfigError(f"{name} must be between 0 and 2")
    return value


def _string_list(value: Any, *, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{name} must be a list of strings")
    if len(value) > MAX_TAGS:
        raise ConfigError(f"{name} must contain at most {MAX_TAGS} entries")
    tags = tuple(item.strip() for item in value if item.strip())
    if any(len(tag) > MAX_TAG_LENGTH for tag in tags):
        raise ConfigError(
            f"{name} entries must be at most {MAX_TAG_LENGTH} characters"
        )
    return tags


def _group(value: Any, *, name: str) -> str:
    if value is None:
        return "未分组"
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a string")
    group = " ".join(value.split())
    if not group:
        raise ConfigError(f"{name} must not be empty")
    if len(group) > 80:
        raise ConfigError(f"{name} must be at most 80 characters")
    return group


def _parse_expected_status(value: Any, *, name: str) -> tuple[int, ...]:
    if value is None:
        return (200,)
    if isinstance(value, int) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{name} must be a non-empty list of HTTP status codes")
    statuses: list[int] = []
    for status in value:
        if isinstance(status, bool) or not isinstance(status, int):
            raise ConfigError(f"{name} entries must be integers")
        if not 100 <= status <= 599:
            raise ConfigError(f"{name} entries must be between 100 and 599")
        statuses.append(status)
    return tuple(statuses)


def _is_host(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    if len(value) > 253 or value.endswith("."):
        return False
    return all(HOST_LABEL.fullmatch(label) for label in value.split("."))


def _environment_name(value: Any, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not ENV_NAME.fullmatch(value):
        raise ConfigError(f"{name} must be a valid environment variable name")
    return value


def _webhook_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("notifications.webhook_url must be a non-empty string")
    url = value.strip()
    if len(url) > MAX_WEBHOOK_URL_LENGTH:
        raise ConfigError(
            "notifications.webhook_url must be at most "
            f"{MAX_WEBHOOK_URL_LENGTH} characters"
        )
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(
            "notifications.webhook_url must be an absolute HTTP(S) URL"
        )
    if parsed.username or parsed.password:
        raise ConfigError("notifications.webhook_url must not contain credentials")
    return url


def _parse_notifications(raw: Any) -> NotificationConfig:
    if raw is None:
        return NotificationConfig()
    if not isinstance(raw, dict):
        raise ConfigError("notifications must be an object")

    webhook_url = _webhook_url(raw.get("webhook_url"))
    webhook_url_env = _environment_name(
        raw.get("webhook_url_env"), name="notifications.webhook_url_env"
    )
    if webhook_url and webhook_url_env:
        raise ConfigError(
            "notifications may use webhook_url or webhook_url_env, not both"
        )
    signing_secret_env = _environment_name(
        raw.get("signing_secret_env"), name="notifications.signing_secret_env"
    )
    cooldown_seconds = _number(
        raw.get("cooldown_seconds"),
        name="notifications.cooldown_seconds",
        default=300,
        minimum=0,
        maximum=86_400,
    )
    timeout_seconds = _number(
        raw.get("timeout_seconds"),
        name="notifications.timeout_seconds",
        default=4,
        minimum=0.2,
        maximum=30,
    )
    retry_attempts = _retry_attempts(
        raw.get("retry_attempts"), name="notifications.retry_attempts"
    )
    return NotificationConfig(
        webhook_url=webhook_url,
        webhook_url_env=webhook_url_env,
        signing_secret_env=signing_secret_env,
        cooldown_seconds=cooldown_seconds,
        timeout_seconds=timeout_seconds,
        retry_attempts=retry_attempts,
    )


def _parse_check(raw: Any, index: int) -> CheckConfig:
    label = f"checks[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{label} must be an object")

    check_id = raw.get("id")
    if not isinstance(check_id, str) or not check_id.strip():
        raise ConfigError(f"{label}.id must be a non-empty string")
    check_id = check_id.strip()
    if not all(char.isalnum() or char in "-_" for char in check_id):
        raise ConfigError(f"{label}.id may only contain letters, digits, '-' and '_'")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{label}.name must be a non-empty string")
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise ConfigError(
            f"{label}.name must be at most {MAX_NAME_LENGTH} characters"
        )

    check_type = raw.get("type")
    if check_type not in SUPPORTED_TYPES:
        supported = ", ".join(sorted(SUPPORTED_TYPES))
        raise ConfigError(f"{label}.type must be one of: {supported}")

    target = raw.get("target")
    if not isinstance(target, str) or not target.strip():
        raise ConfigError(f"{label}.target must be a non-empty string")
    target = target.strip()
    if len(target) > MAX_TARGET_LENGTH:
        raise ConfigError(
            f"{label}.target must be at most {MAX_TARGET_LENGTH} characters"
        )

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"{label}.enabled must be a boolean")

    verify_tls = raw.get("verify_tls", True)
    if not isinstance(verify_tls, bool):
        raise ConfigError(f"{label}.verify_tls must be a boolean")

    port = _port(raw.get("port"), name=f"{label}.port")
    if check_type in {"tcp", "tls"} and port is None:
        port = 443 if check_type == "tls" else None
    if check_type == "tcp" and port is None:
        raise ConfigError(f"{label}.port is required for TCP checks")

    if check_type == "http":
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigError(f"{label}.target must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ConfigError(f"{label}.target must not contain credentials")
    elif "://" in target or "/" in target:
        raise ConfigError(f"{label}.target must be a hostname for {check_type} checks")
    elif not _is_host(target):
        raise ConfigError(f"{label}.target is not a valid hostname or IP address")

    timeout = _number(
        raw.get("timeout_seconds"),
        name=f"{label}.timeout_seconds",
        default=5.0,
        minimum=0.2,
        maximum=60,
    )

    return CheckConfig(
        id=check_id,
        name=name,
        type=check_type,
        target=target,
        enabled=enabled,
        port=port,
        expected_status=_parse_expected_status(
            raw.get("expected_status"), name=f"{label}.expected_status"
        ),
        timeout_seconds=timeout,
        retry_attempts=_retry_attempts(
            raw.get("retry_attempts"), name=f"{label}.retry_attempts"
        ),
        verify_tls=verify_tls,
        group=_group(raw.get("group"), name=f"{label}.group"),
        tags=_string_list(raw.get("tags"), name=f"{label}.tags"),
    )


def parse_config(raw: Any) -> DashboardConfig:
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be an object")

    version = raw.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ConfigError("version must be 1")

    threshold_raw = raw.get("thresholds", {})
    if not isinstance(threshold_raw, dict):
        raise ConfigError("thresholds must be an object")
    thresholds = Thresholds(
        latency_warn_ms=_number(
            threshold_raw.get("latency_warn_ms"),
            name="thresholds.latency_warn_ms",
            default=800,
            minimum=1,
            maximum=60_000,
        ),
        latency_fail_ms=_number(
            threshold_raw.get("latency_fail_ms"),
            name="thresholds.latency_fail_ms",
            default=2500,
            minimum=1,
            maximum=120_000,
        ),
        tls_warn_days=_number(
            threshold_raw.get("tls_warn_days"),
            name="thresholds.tls_warn_days",
            default=30,
            minimum=1,
            maximum=3650,
        ),
        tls_fail_days=_number(
            threshold_raw.get("tls_fail_days"),
            name="thresholds.tls_fail_days",
            default=7,
            minimum=1,
            maximum=3650,
        ),
    )
    monitor_interval_seconds = _number(
        raw.get("monitor_interval_seconds"),
        name="monitor_interval_seconds",
        default=60,
        minimum=10,
        maximum=3600,
    )
    notifications = _parse_notifications(raw.get("notifications"))

    checks_raw = raw.get("checks")
    if not isinstance(checks_raw, list) or not checks_raw:
        raise ConfigError("checks must be a non-empty list")
    if len(checks_raw) > MAX_CHECKS:
        raise ConfigError(f"checks must contain at most {MAX_CHECKS} entries")
    checks = tuple(_parse_check(item, index) for index, item in enumerate(checks_raw))
    ids = [check.id for check in checks]
    if len(ids) != len(set(ids)):
        raise ConfigError("check ids must be unique")

    try:
        maintenance_windows = parse_maintenance_windows(
            raw.get("maintenance_windows")
        )
    except MaintenanceError as exc:
        raise ConfigError(str(exc)) from exc
    known_ids = set(ids)
    for window in maintenance_windows:
        unknown = [check_id for check_id in window.check_ids if check_id not in known_ids]
        if unknown:
            # A typo must fail loudly instead of silently disabling nothing.
            raise ConfigError(
                f"maintenance_windows[{window.id}].check_ids references unknown "
                f"check ids: {', '.join(unknown)}"
            )

    return DashboardConfig(
        version=version,
        thresholds=thresholds,
        checks=checks,
        monitor_interval_seconds=monitor_interval_seconds,
        notifications=notifications,
        maintenance_windows=maintenance_windows,
    )


def load_config(path: str | Path) -> DashboardConfig:
    config_path = Path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid JSON in {config_path}: line {exc.lineno}, column {exc.colno}"
        ) from exc
    return parse_config(raw)

