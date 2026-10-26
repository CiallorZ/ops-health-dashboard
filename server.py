"""Zero-dependency local web server for the operations health dashboard."""

from __future__ import annotations

import argparse
import json
import mimetypes
import posixpath
import signal
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from monitor import __version__
from monitor.alerts import create_alert_dispatcher
from monitor.config import ConfigError, load_config
from monitor.instance_lock import InstanceLock, InstanceLockError
from monitor.history import MAX_TREND_DAYS, HistoryStore
from monitor.report import build_report
from monitor.runner import CheckRunnerService
from monitor.scheduler import BackgroundMonitor

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DASHBOARD = PROJECT_ROOT / "dashboard"
STARTED_AT = time.monotonic()
SERVER_VERSION = f"OpsHealthDashboard/{__version__}"


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        runner: CheckRunnerService,
        dashboard_dir: Path,
        scheduler: BackgroundMonitor,
    ) -> None:
        super().__init__(address, DashboardRequestHandler)
        self.runner = runner
        self.dashboard_dir = dashboard_dir.resolve()
        self.scheduler = scheduler
        self.lock: InstanceLock | None = None

    def start_background_monitor(self) -> None:
        self.scheduler.start()

    def hold_lock(self, lock: InstanceLock) -> None:
        self.lock = lock

    def server_close(self) -> None:
        self.scheduler.stop()
        if self.runner.alert_dispatcher is not None:
            self.runner.alert_dispatcher.close()
        if self.lock is not None:
            self.lock.release()
        super().server_close()


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    server_version = SERVER_VERSION
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "ops-health-dashboard",
                    "version": __version__,
                    "uptime_seconds": round(time.monotonic() - STARTED_AT, 1),
                    "scheduler": self.server.scheduler.status(),
                    "retention": self.server.runner.history.stats(),
                },
            )
            return
        if parsed.path == "/healthz":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "ops-health-dashboard",
                    "version": __version__,
                    "uptime_seconds": round(time.monotonic() - STARTED_AT, 1),
                },
            )
            return
        if parsed.path == "/readyz":
            try:
                problems: list[str] = []
                snapshot = self.server.runner.get_snapshot(force=False)
                if snapshot is None:
                    problems.append("snapshot unavailable")
                else:
                    try:
                        self.server.runner.history.stats()
                    except OSError as exc:
                        problems.append(f"data directory not writable: {exc}")
                sched = self.server.scheduler.status()
                if not sched.get("running"):
                    problems.append("scheduler not running")
            except Exception as exc:  # keep /readyz honest under partial failures
                problems.append(str(exc))
            if problems:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "status": "not-ready",
                        "service": "ops-health-dashboard",
                        "version": __version__,
                        "problems": problems,
                    },
                )
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ready",
                    "service": "ops-health-dashboard",
                    "version": __version__,
                },
            )
            return
        if parsed.path == "/metrics":
            body = self.server.runner.metrics_payload().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self._security_headers()
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/status":
            query = parse_qs(parsed.query)
            force = query.get("force", ["0"])[0].lower() in {"1", "true", "yes"}
            self._run_snapshot(force=force)
            return
        if parsed.path == "/api/history":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["40"])[0])
            except ValueError:
                limit = 40
            self._send_json(
                HTTPStatus.OK,
                {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "items": self.server.runner.history.recent(limit),
                },
            )
            return
        if parsed.path == "/api/config":
            self._send_json(HTTPStatus.OK, self.server.runner.config.public_dict())
            return
        if parsed.path == "/api/trends":
            query = parse_qs(parsed.query)
            try:
                days = int(query.get("days", ["7"])[0])
            except ValueError:
                days = 7
            self._send_json(HTTPStatus.OK, self._trends(days))
            return
        if parsed.path == "/api/alerts":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["12"])[0])
            except ValueError:
                limit = 12
            self._send_json(
                HTTPStatus.OK,
                {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    **self.server.runner.alert_status(limit=max(1, min(limit, 40))),
                },
            )
            return
        if parsed.path == "/api/certificates":
            self._send_json(HTTPStatus.OK, self._certificates())
            return
        if parsed.path == "/api/maintenance":
            self._send_json(HTTPStatus.OK, self._maintenance())
            return
        if parsed.path == "/api/report":
            self._send_report()
            return
        if parsed.path.startswith("/api/"):
            self._send_error(HTTPStatus.NOT_FOUND, "unknown API endpoint")
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/refresh":
            self._run_snapshot(force=True)
            return
        self._send_error(HTTPStatus.NOT_FOUND, "unknown API endpoint")

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._send_error(HTTPStatus.METHOD_NOT_ALLOWED, "HEAD is not supported here")
            return
        self._serve_static(parsed.path, head_only=True)

    def _run_snapshot(self, *, force: bool) -> None:
        try:
            snapshot = self.server.runner.get_snapshot(force=force, history_limit=40)
        except Exception as exc:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"snapshot failed: {type(exc).__name__}",
            )
            return
        self._send_json(HTTPStatus.OK, self._with_runtime(snapshot))

    def _with_runtime(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            **snapshot,
            "automation": {
                "scheduler": self.server.scheduler.status(),
                "alerts": self.server.runner.alert_status(limit=12),
                "retention": self.server.runner.history.stats(),
                "maintenance": self.server.runner.get_maintenance(),
            },
        }

    def _trends(self, days: int) -> dict[str, Any]:
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **self.server.runner.get_trends(days=days),
        }

    def _certificates(self) -> dict[str, Any]:
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **self.server.runner.get_certificates(),
        }

    def _maintenance(self) -> dict[str, Any]:
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **self.server.runner.get_maintenance(),
        }

    def _send_report(self) -> None:
        try:
            snapshot = self.server.runner.get_snapshot(history_limit=40)
            skipped = tuple(
                check.id for check in self.server.runner.config.checks if not check.enabled
            )
            data = build_report(snapshot, skipped_check_ids=skipped)
        except Exception as exc:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"report failed: {type(exc).__name__}",
            )
            return
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", 'attachment; filename="sentinel-report.html"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, path: str, *, head_only: bool = False) -> None:
        decoded = unquote(path)
        relative = "index.html" if decoded in {"", "/"} else decoded.lstrip("/")
        normalized = posixpath.normpath(relative)
        if normalized.startswith("../") or normalized in {"..", "."}:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        target = (self.server.dashboard_dir / normalized).resolve()
        try:
            target.relative_to(self.server.dashboard_dir)
        except ValueError:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        if not target.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return

        content_type, _ = mimetypes.guess_type(target.name)
        content_type = content_type or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message, "status": status.value})

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'",
        )

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(
            f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}\n"
        )


def build_server(
    *,
    host: str,
    port: int,
    config_path: str | Path,
    data_dir: str | Path,
    dashboard_dir: str | Path = DEFAULT_DASHBOARD,
    cache_seconds: float = 8.0,
) -> DashboardServer:
    config = load_config(config_path)
    lock = InstanceLock(Path(data_dir))
    try:
        lock.acquire()
    except InstanceLockError as exc:
        print(f"startup failed: {exc}", file=sys.stderr)
        raise
    alert_dispatcher = None
    try:
        history = HistoryStore(data_dir)
        alert_dispatcher = create_alert_dispatcher(config.notifications, data_dir)
        runner = CheckRunnerService(
            config,
            history,
            cache_seconds=cache_seconds,
            alert_dispatcher=alert_dispatcher,
        )
        scheduler = BackgroundMonitor(runner, config.monitor_interval_seconds)
        server = DashboardServer((host, port), runner, Path(dashboard_dir), scheduler)
    except BaseException:
        try:
            if alert_dispatcher is not None:
                alert_dispatcher.close()
        finally:
            lock.release()
        raise
    server.hold_lock(lock)
    return server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ops-health-dashboard local control plane."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "checks.json"))
    parser.add_argument("--data-dir", default=str(PROJECT_ROOT / "data"))
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="Disable automatic background sampling for this process.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ops-health-dashboard {__version__}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        server = build_server(
            host=args.host,
            port=args.port,
            config_path=args.config,
            data_dir=args.data_dir,
        )
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except InstanceLockError as exc:
        print(f"startup failed: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"Server startup failed: {exc}", file=sys.stderr)
        return 1

    def stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    print(
        f"ops-health-dashboard {__version__} listening on "
        f"http://{args.host}:{server.server_address[1]}"
    )
    if args.no_scheduler:
        print("background scheduler: disabled")
    else:
        server.start_background_monitor()
        print(
            "background scheduler: "
            f"every {server.runner.config.monitor_interval_seconds:g}s"
        )
    print(f"config: {Path(args.config).resolve()}")
    print("press Ctrl+C to stop")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

