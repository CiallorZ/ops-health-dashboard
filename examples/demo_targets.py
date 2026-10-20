"""Local HTTP targets used by examples/checks.demo.json for demos and screenshots."""

from __future__ import annotations

import argparse
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DemoHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    counts: dict[str, int] = {}
    lock = threading.Lock()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path == "/slow":
            time.sleep(1.2)
        if path == "/flaky":
            with self.lock:
                count = self.counts.get(path, 0) + 1
                self.counts[path] = count
            # Fail every odd call so any fresh snapshot demonstrates recovery.
            if count % 2 == 1:
                self._send(500)
                return
        self._send(200)

    def _send(self, status: int) -> None:
        body = b'{"ok":true}' if status == 200 else b'{"ok":false}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--legacy-port", type=int, default=18082)
    parser.add_argument(
        "--legacy-accepts",
        type=int,
        default=3,
        help="Accept this many TCP handshakes before closing the legacy port.",
    )
    args = parser.parse_args()

    legacy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    legacy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    legacy.bind(("127.0.0.1", args.legacy_port))
    legacy.listen(8)

    def serve_legacy() -> None:
        for _ in range(max(0, args.legacy_accepts)):
            try:
                connection, _peer = legacy.accept()
            except OSError:
                return
            connection.close()
        legacy.close()

    threading.Thread(target=serve_legacy, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    print(
        f"demo targets listening on http://127.0.0.1:{args.port} "
        f"(legacy TCP {args.legacy_port}, closes after {args.legacy_accepts} handshakes)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
