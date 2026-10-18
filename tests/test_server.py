import json
import threading
import unittest
import urllib.request
from tempfile import TemporaryDirectory

from server import build_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        dashboard = f"{self.temp.name}/dashboard"
        from pathlib import Path

        Path(dashboard).mkdir()
        Path(f"{dashboard}/index.html").write_text("<h1>test</h1>", encoding="utf-8")
        config = f"{self.temp.name}/checks.json"
        Path(config).write_text(
            json.dumps(
                {
                    "version": 1,
                    "checks": [
                        {
                            "id": "self",
                            "name": "Self",
                            "type": "ping",
                            "target": "127.0.0.1",
                            "timeout_seconds": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            config_path=config,
            data_dir=f"{self.temp.name}/data",
            dashboard_dir=dashboard,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def get_json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, response.headers, json.loads(response.read())

    def test_health(self):
        status, headers, body = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(headers["Content-Security-Policy"].startswith("default-src"), True)

    def test_config_exposes_no_secrets(self):
        status, _, body = self.get_json("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(body["checks"][0]["id"], "self")

    def test_unknown_api_is_json_404(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(self.base + "/api/nope", timeout=5)
        error = raised.exception
        self.assertEqual(error.code, 404)
        error.close()

    def test_static_index(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"test", response.read())

    def test_report_is_downloadable_and_escapes_untrusted_values(self):
        self.server.runner.get_snapshot = lambda **_kwargs: {
            "generated_at": "2026-10-18T12:00:00Z",
            "summary": {"health": "critical", "total": 1, "ok": 0, "warn": 0, "fail": 1},
            "checks": [{
                "name": "<script>alert(1)</script>",
                "type": "http",
                "target": "https://user:secret@example.test/path?token=secret#fragment",
                "status": "fail",
                "summary": "HTTP 503",
                "detail": "service unavailable",
                "latency_ms": None,
            }],
        }
        with urllib.request.urlopen(self.base + "/api/report", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
            self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("https://example.test/path", body)
        self.assertNotIn("secret", body)

    def test_report_handles_invalid_url_port_without_exposing_query(self):
        self.server.runner.get_snapshot = lambda **_kwargs: {
            "generated_at": "2026-10-18T12:00:00Z",
            "summary": {},
            "checks": [{
                "name": "Broken URL",
                "type": "http",
                "target": "https://example.test:bad/path?token=secret",
                "status": "fail",
                "summary": "failed",
                "detail": "bad URL",
                "latency_ms": None,
            }],
        }
        with urllib.request.urlopen(self.base + "/api/report", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
        self.assertIn("https://example.test/path", body)
        self.assertNotIn("secret", body)


if __name__ == "__main__":
    unittest.main()

