import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe") and shutil.which("pythonw.exe"),
                     "Windows PowerShell and pythonw are required")
class LauncherTests(unittest.TestCase):
    def run_with_health(self, payload):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "scripts").mkdir()
                shutil.copy(ROOT / "scripts" / "run-server.ps1", root / "scripts")
                (root / "VERSION").write_text("9.9.9", encoding="ascii")
                # Prevent a real server launch; this child must exit immediately.
                (root / "server.py").write_text("raise SystemExit(1)\n", encoding="ascii")
                return subprocess.run(
                    ["powershell.exe", "-NoProfile", "-File", str(root / "scripts" / "run-server.ps1"),
                     "-Port", str(server.server_port)], capture_output=True, timeout=15,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_does_not_treat_unrelated_http_200_as_existing_server(self):
        result = self.run_with_health({"status": "ok", "service": "unrelated", "version": "9.9.9"})
        self.assertNotEqual(result.returncode, 0)

    def test_recognizes_matching_health_contract(self):
        result = self.run_with_health({"status": "ok", "service": "ops-health-dashboard", "version": "9.9.9"})
        self.assertEqual(result.returncode, 0)

    def test_rejects_different_sentinel_version(self):
        result = self.run_with_health({"status": "ok", "service": "ops-health-dashboard", "version": "0.0.1"})
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
