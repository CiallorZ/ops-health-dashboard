"""Network checks with bounded timeouts and normalized results."""

from __future__ import annotations

import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .config import CheckConfig, Thresholds


@dataclass
class CheckResult:
    id: str
    name: str
    type: str
    target: str
    port: int | None
    status: str
    summary: str
    detail: str
    latency_ms: float | None
    checked_at: str
    tags: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "target": self.target,
            "port": self.port,
            "status": self.status,
            "summary": self.summary,
            "detail": self.detail,
            "latency_ms": (
                round(self.latency_ms, 1) if self.latency_ms is not None else None
            ),
            "checked_at": self.checked_at,
            "tags": list(self.tags),
            "metrics": self.metrics,
        }


class CheckExecutionError(RuntimeError):
    """A check failed in a way that should be shown to the operator."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _latency_status(
    latency_ms: float, thresholds: Thresholds
) -> tuple[str, str]:
    if latency_ms >= thresholds.latency_fail_ms:
        return "fail", "延迟超过失败阈值"
    if latency_ms >= thresholds.latency_warn_ms:
        return "warn", "延迟超过告警阈值"
    return "ok", "响应正常"


def _base_result(
    check: CheckConfig,
    *,
    status: str,
    summary: str,
    detail: str,
    latency_ms: float | None,
    metrics: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        id=check.id,
        name=check.name,
        type=check.type,
        target=check.target,
        port=check.port,
        status=status,
        summary=summary,
        detail=detail,
        latency_ms=latency_ms,
        checked_at=isoformat(utc_now()),
        tags=check.tags,
        metrics=metrics or {},
    )


def _run_ping(check: CheckConfig, thresholds: Thresholds) -> CheckResult:
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creation_flags = subprocess.CREATE_NO_WINDOW
        command = [
            "ping",
            "-n",
            "1",
            "-w",
            str(max(1, int(check.timeout_seconds * 1000))),
            check.target,
        ]
    else:
        creation_flags = 0
        command = [
            "ping",
            "-c",
            "1",
            "-W",
            str(max(1, int(check.timeout_seconds))),
            check.target,
        ]

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=check.timeout_seconds + 1,
            check=False,
            creationflags=creation_flags,
        )
    except FileNotFoundError as exc:
        raise CheckExecutionError("系统没有可用的 ping 命令") from exc
    except subprocess.TimeoutExpired as exc:
        raise CheckExecutionError("ping 命令执行超时") from exc

    latency_ms = (time.perf_counter() - started) * 1000
    if completed.returncode != 0:
        raise CheckExecutionError("ICMP 无响应，或当前环境禁止 ping")
    status, _ = _latency_status(latency_ms, thresholds)
    return _base_result(
        check,
        status=status,
        summary="ICMP 可达",
        detail="主机已回应 ICMP Echo",
        latency_ms=latency_ms,
        metrics={"return_code": completed.returncode},
    )


def _run_tcp(check: CheckConfig, thresholds: Thresholds) -> CheckResult:
    started = time.perf_counter()
    try:
        with socket.create_connection(
            (check.target, int(check.port or 0)), timeout=check.timeout_seconds
        ) as connection:
            peer = connection.getpeername()
    except socket.timeout as exc:
        raise CheckExecutionError("TCP 连接超时") from exc
    except OSError as exc:
        raise CheckExecutionError(f"TCP 连接失败：{exc.strerror or exc}") from exc

    latency_ms = (time.perf_counter() - started) * 1000
    status, _ = _latency_status(latency_ms, thresholds)
    return _base_result(
        check,
        status=status,
        summary="端口可达",
        detail=f"TCP {check.target}:{check.port} 握手成功",
        latency_ms=latency_ms,
        metrics={"peer": list(peer) if isinstance(peer, tuple) else str(peer)},
    )


def _ssl_context(check: CheckConfig) -> ssl.SSLContext:
    if check.verify_tls:
        return ssl.create_default_context()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _run_tls(check: CheckConfig, thresholds: Thresholds) -> CheckResult:
    started = time.perf_counter()
    try:
        with socket.create_connection(
            (check.target, int(check.port or 443)), timeout=check.timeout_seconds
        ) as raw_socket:
            with _ssl_context(check).wrap_socket(
                raw_socket, server_hostname=check.target
            ) as tls_socket:
                certificate = tls_socket.getpeercert()
    except socket.timeout as exc:
        raise CheckExecutionError("TLS 连接超时") from exc
    except ssl.SSLError as exc:
        reason = getattr(exc, "reason", None) or str(exc)
        raise CheckExecutionError(f"TLS 握手失败：{reason}") from exc
    except OSError as exc:
        raise CheckExecutionError(f"TLS 连接失败：{exc.strerror or exc}") from exc

    latency_ms = (time.perf_counter() - started) * 1000
    if not certificate or not certificate.get("notAfter"):
        raise CheckExecutionError("TLS 服务未返回可读取的证书")

    expires_at = datetime.fromtimestamp(
        ssl.cert_time_to_seconds(certificate["notAfter"]), tz=timezone.utc
    )
    remaining_days = (expires_at - utc_now()).total_seconds() / 86400
    if remaining_days <= thresholds.tls_fail_days:
        status = "fail"
        summary = "证书即将过期"
    elif remaining_days <= thresholds.tls_warn_days:
        status = "warn"
        summary = "证书需要续期"
    else:
        status = "ok"
        summary = "证书有效"

    subject = certificate.get("subject", ())
    common_name = ""
    for entry in subject:
        for key, value in entry:
            if key == "commonName":
                common_name = value
                break

    return _base_result(
        check,
        status=status,
        summary=summary,
        detail=f"证书剩余约 {max(0, int(remaining_days))} 天",
        latency_ms=latency_ms,
        metrics={
            "remaining_days": round(remaining_days, 1),
            "expires_at": isoformat(expires_at),
            "common_name": common_name,
            "verify_tls": check.verify_tls,
        },
    )


def _run_http(check: CheckConfig, thresholds: Thresholds) -> CheckResult:
    request = urllib.request.Request(
        check.target,
        headers={
            "User-Agent": "ops-health-dashboard/0.1",
            "Accept": "*/*",
        },
        method="GET",
    )
    context = _ssl_context(check)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(
            request, timeout=check.timeout_seconds, context=context
        ) as response:
            status_code = response.status
            final_url = response.geturl()
            response.read(1)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        final_url = exc.geturl()
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise CheckExecutionError(f"HTTP 请求失败：{reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise CheckExecutionError("HTTP 请求超时") from exc

    latency_ms = (time.perf_counter() - started) * 1000
    if status_code not in check.expected_status:
        expected = ", ".join(str(item) for item in check.expected_status)
        return _base_result(
            check,
            status="fail",
            summary=f"HTTP {status_code}",
            detail=f"状态码不在预期范围（期望 {expected}）",
            latency_ms=latency_ms,
            metrics={"status_code": status_code, "final_url": final_url},
        )

    status, latency_note = _latency_status(latency_ms, thresholds)
    return _base_result(
        check,
        status=status,
        summary=f"HTTP {status_code}",
        detail=latency_note,
        latency_ms=latency_ms,
        metrics={"status_code": status_code, "final_url": final_url},
    )


def run_check(
    check: CheckConfig,
    thresholds: Thresholds,
) -> CheckResult:
    """Run one check and always return a renderable result."""
    try:
        if check.type == "ping":
            return _run_ping(check, thresholds)
        if check.type == "tcp":
            return _run_tcp(check, thresholds)
        if check.type == "tls":
            return _run_tls(check, thresholds)
        if check.type == "http":
            return _run_http(check, thresholds)
        raise CheckExecutionError(f"不支持的检查类型：{check.type}")
    except CheckExecutionError as exc:
        return _base_result(
            check,
            status="fail",
            summary="检测失败",
            detail=str(exc),
            latency_ms=None,
        )
    except Exception as exc:  # Keep one broken check from taking down the run.
        return _base_result(
            check,
            status="fail",
            summary="检测异常",
            detail=f"未预期错误：{type(exc).__name__}: {exc}",
            latency_ms=None,
        )

