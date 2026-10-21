import json
import threading
import unittest
import urllib.request
from tempfile import TemporaryDirectory

from monitor import __version__
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
                    "monitor_interval_seconds": 60,
                    "notifications": {
                        "webhook_url": "http://127.0.0.1:9/hook?token=server-secret"
                    },
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
        self.assertEqual(body["version"], __version__)
        self.assertIn(f"OpsHealthDashboard/{__version__}", headers["Server"])
        self.assertEqual(headers["Content-Security-Policy"].startswith("default-src"), True)

    def test_config_exposes_no_secrets(self):
        status, _, body = self.get_json("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(body["checks"][0]["id"], "self")
        self.assertTrue(body["notifications"]["configured"])
        self.assertNotIn("server-secret", json.dumps(body))
        self.assertNotIn("/hook", json.dumps(body))

    def test_alerts_endpoint_is_redacted_and_bounded(self):
        status, _, body = self.get_json("/api/alerts?limit=999")
        self.assertEqual(status, 200)
        self.assertTrue(body["configured"])
        self.assertIsInstance(body["recent"], list)
        self.assertNotIn("server-secret", json.dumps(body))
        self.assertNotIn("/hook", json.dumps(body))

    def test_trends_endpoint_defaults_and_clamps_days(self):
        self.server.runner.history.append(
            {
                "run_id": "run-injected",
                "generated_at": "2026-10-19T00:00:00Z",
                "checks": [{"id": "self", "status": "fail", "latency_ms": None}],
            }
        )

        status, _, body = self.get_json("/api/trends")
        self.assertEqual(status, 200)
        self.assertEqual(body["days"], 7)
        self.assertEqual(body["days_with_data"], 2)
        self.assertTrue(body["generated_from_utc_days"])
        injected_day = body["daily"]["2026-10-19"]
        self.assertEqual(injected_day["samples"], 1)
        self.assertEqual(injected_day["fail"], 1)
        self.assertEqual(injected_day["availability_percent"], 0.0)
        self.assertIsNone(injected_day["p50_latency_ms"])
        self.assertEqual(body["checks"]["self"]["totals"]["fail"], 1)

        status, _, clamped = self.get_json("/api/trends?days=999")
        self.assertEqual(status, 200)
        self.assertEqual(clamped["days"], 30)

        status, _, invalid = self.get_json("/api/trends?days=soon")
        self.assertEqual(status, 200)
        self.assertEqual(invalid["days"], 7)

    def test_status_exposes_background_scheduler_state(self):
        status, _, body = self.get_json("/api/status?force=1")
        self.assertEqual(status, 200)
        self.assertIn("automation", body)
        self.assertIn("scheduler", body["automation"])
        self.assertEqual(
            body["automation"]["scheduler"]["interval_seconds"], 60
        )
        self.assertFalse(body["automation"]["scheduler"]["running"])

    def test_certificates_endpoint_reports_bounded_calendar(self):
        status, _, body = self.get_json("/api/certificates")
        self.assertEqual(status, 200)
        self.assertEqual(body["tracked"], 0)
        self.assertEqual(body["upcoming"], [])
        self.assertEqual(body["counts"], {
            "expired": 0,
            "critical": 0,
            "warning": 0,
            "healthy": 0,
        })
        self.assertEqual(body["thresholds"]["tls_warn_days"], 30)
        self.assertEqual(body["thresholds"]["tls_fail_days"], 7)

    def test_health_and_status_expose_history_retention_bounds(self):
        _, _, health = self.get_json("/api/health")
        retention = health["retention"]
        self.assertGreater(retention["max_file_bytes"], 0)
        self.assertGreaterEqual(retention["max_archive_files"], 0)
        self.assertGreater(retention["max_total_bytes"], retention["max_file_bytes"])
        self.assertIsInstance(retention["archives"], list)
        self.assertFalse(retention["truncated"])

        _, _, status = self.get_json("/api/status?force=1")
        status_retention = status["automation"]["retention"]
        self.assertEqual(
            status_retention["max_file_bytes"], retention["max_file_bytes"]
        )
        self.assertGreaterEqual(status_retention["current_bytes"], retention["current_bytes"])
        self.assertLessEqual(
            status_retention["total_bytes"], status_retention["max_total_bytes"]
        )

    def test_certificates_endpoint_hides_metrics_from_non_tls_checks(self):
        self.server.runner.get_snapshot = lambda **_kwargs: {
            "generated_at": "2026-10-21T00:00:00Z",
            "summary": {},
            "checks": [
                {
                    "id": "plain-http",
                    "name": "Plain HTTP",
                    "type": "http",
                    "target": "http://127.0.0.1/",
                    "status": "ok",
                    "metrics": {"status_code": 200},
                }
            ],
        }
        status, _, body = self.get_json("/api/certificates")
        self.assertEqual(status, 200)
        self.assertEqual(body["tracked"], 0)

    def test_maintenance_endpoint_reports_no_windows_by_default(self):
        status, _, body = self.get_json("/api/maintenance")
        self.assertEqual(status, 200)
        self.assertFalse(body["configured"])
        self.assertEqual(body["active"], [])
        self.assertEqual(body["upcoming"], [])
        self.assertEqual(body["active_check_ids"], [])

        status, _, snapshot = self.get_json("/api/status?force=1")
        self.assertEqual(status, 200)
        self.assertIn("maintenance", snapshot["automation"])
        self.assertIn("retention", snapshot["automation"])

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
                "group": "<b>核心服务</b>",
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
        self.assertIn("&lt;b&gt;核心服务&lt;/b&gt;", body)

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

