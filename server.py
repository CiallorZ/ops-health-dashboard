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
from monitor.config import ConfigError, load_config
from monitor.history import HistoryStore
from monitor.runner import CheckRunnerService
from toolbox.errors import ToolError
from toolbox.registry import execute_tool, list_tools

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DASHBOARD = PROJECT_ROOT / "dashboard"
STARTED_AT = time.monotonic()
MAX_JSON_BODY_BYTES = 64 * 1024


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        runner: CheckRunnerService,
        dashboard_dir: Path,
    ) -> None:
        super().__init__(address, DashboardRequestHandler)
        self.runner = runner
        self.dashboard_dir = dashboard_dir.resolve()


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    server_version = "OpsHealthDashboard/0.2"
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
                },
            )
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
        if parsed.path == "/api/tools":
            self._send_json(HTTPStatus.OK, {"tools": list_tools()})
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
        if parsed.path == "/api/tools/run":
            self._run_tool()
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
        self._send_json(HTTPStatus.OK, snapshot)

    def _run_tool(self) -> None:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type != "application/json":
            self._send_error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "Content-Type must be application/json",
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_JSON_BODY_BYTES:
            self._send_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE
                if length > MAX_JSON_BODY_BYTES
                else HTTPStatus.BAD_REQUEST,
                "request body must be between 1 and 65536 bytes",
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error(HTTPStatus.BAD_REQUEST, "request body must be valid JSON")
            return
        if not isinstance(payload, dict):
            self._send_error(HTTPStatus.BAD_REQUEST, "request body must be an object")
            return

        tool_id = payload.get("tool")
        inputs = payload.get("inputs")
        if not isinstance(tool_id, str) or not tool_id.strip():
            self._send_error(HTTPStatus.BAD_REQUEST, "tool must be a non-empty string")
            return
        try:
            result = execute_tool(tool_id.strip(), inputs)
        except ToolError as exc:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": exc.public_dict(), "status": HTTPStatus.BAD_REQUEST.value},
            )
            return
        except Exception as exc:  # Do not expose tracebacks or local details.
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"tool failed: {type(exc).__name__}",
            )
            return
        self._send_json(HTTPStatus.OK, {"tool": tool_id, "result": result})

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
    history = HistoryStore(data_dir)
    runner = CheckRunnerService(config, history, cache_seconds=cache_seconds)
    return DashboardServer((host, port), runner, Path(dashboard_dir))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ops-health-dashboard local control plane."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "checks.json"))
    parser.add_argument("--data-dir", default=str(PROJECT_ROOT / "data"))
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

