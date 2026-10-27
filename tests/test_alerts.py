import hashlib
import hmac
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tempfile import TemporaryDirectory

from monitor.alerts import (
    AlertDispatcher,
    AlertStore,
    _event_name,
    resolve_notification_settings,
)
from monitor.checks import CheckResult, isoformat, utc_now
from monitor.config import ConfigError, NotificationConfig


class CaptureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests = []
    response_codes = []
    lock = threading.Lock()

    @classmethod
    def reset(cls, codes):
        with cls.lock:
            cls.requests = []
            cls.response_codes = list(codes)

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        with self.lock:
            self.requests.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body,
                }
            )
            code = self.response_codes.pop(0) if self.response_codes else 204
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, _fmt, *_args):
        return


def result(status="fail"):
    return CheckResult(
        id="api",
        name="生产 API",
        type="http",
        target="https://example.test/health?token=target-secret",
        port=None,
        status=status,
        summary="HTTP 503",
        detail="upstream unavailable",
        latency_ms=33.4,
        checked_at=isoformat(utc_now()),
        group="核心服务",
    )


class AlertTests(unittest.TestCase):
    def test_unknown_does_not_claim_recovery(self):
        self.assertEqual(_event_name("fail", "unknown"), "status_change")
        self.assertEqual(_event_name("fail", "ok"), "recovered")

    def setUp(self):
        CaptureHandler.reset([204])
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/hook"
        self.temp = TemporaryDirectory()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def dispatcher(self, *, secret=None, cooldown=0, retries=0):
        dispatcher = AlertDispatcher(
            self.base + "?token=webhook-secret",
            signing_secret=secret,
            cooldown_seconds=cooldown,
            timeout_seconds=2,
            retry_attempts=retries,
            store=AlertStore(self.temp.name),
        )
        self.addCleanup(dispatcher.close)
        return dispatcher

    def test_signed_delivery_redacts_webhook_and_target_query(self):
        dispatcher = self.dispatcher(secret="signing-secret")
        dispatcher.notify_transition(
            result(),
            None,
            {"health": "critical", "total": 1, "ok": 0, "warn": 0, "fail": 1},
        )
        self.assertTrue(dispatcher.wait_for_idle(5))

        self.assertEqual(len(CaptureHandler.requests), 1)
        request = CaptureHandler.requests[0]
        payload = json.loads(request["body"])
        timestamp = request["headers"]["X-Sentinel-Timestamp"]
        expected = hmac.new(
            b"signing-secret",
            timestamp.encode("ascii") + b"." + request["body"],
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(
            request["headers"]["X-Sentinel-Signature"], f"sha256={expected}"
        )
        self.assertEqual(payload["monitor"]["target"], "https://example.test/health")
        self.assertNotIn("target-secret", json.dumps(payload))
        self.assertNotIn("webhook-secret", json.dumps(dispatcher.status()))
        self.assertEqual(dispatcher.status()["recent"][0]["status"], "delivered")

    def test_cooldown_suppresses_duplicate_transition(self):
        dispatcher = self.dispatcher(cooldown=60)
        summary = {"health": "critical", "total": 1, "ok": 0, "warn": 0, "fail": 1}
        dispatcher.notify_transition(result(), None, summary)
        dispatcher.notify_transition(result(), None, summary)
        self.assertTrue(dispatcher.wait_for_idle(5))

        self.assertEqual(len(CaptureHandler.requests), 1)
        statuses = {item["status"] for item in dispatcher.status()["recent"]}
        self.assertIn("delivered", statuses)
        self.assertIn("suppressed", statuses)

    def test_server_errors_retry_until_bounded_limit(self):
        CaptureHandler.reset([500, 503, 204])
        dispatcher = self.dispatcher(retries=2)
        dispatcher.notify_transition(
            result(),
            None,
            {"health": "critical", "total": 1, "ok": 0, "warn": 0, "fail": 1},
        )
        self.assertTrue(dispatcher.wait_for_idle(5))

        self.assertEqual(len(CaptureHandler.requests), 3)
        record = dispatcher.status()["recent"][0]
        self.assertEqual(record["status"], "delivered")
        self.assertEqual(record["attempts"], 3)
        self.assertEqual(record["http_status"], 204)

    def test_client_errors_do_not_retry(self):
        CaptureHandler.reset([400, 204])
        dispatcher = self.dispatcher(retries=2)
        dispatcher.notify_transition(
            result(),
            None,
            {"health": "critical", "total": 1, "ok": 0, "warn": 0, "fail": 1},
        )
        self.assertTrue(dispatcher.wait_for_idle(5))

        self.assertEqual(len(CaptureHandler.requests), 1)
        record = dispatcher.status()["recent"][0]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["attempts"], 1)
        self.assertEqual(record["http_status"], 400)

    def test_environment_secret_must_exist(self):
        config = NotificationConfig(
            webhook_url_env="SENTINEL_WEBHOOK_URL",
            signing_secret_env="SENTINEL_WEBHOOK_SECRET",
        )
        with self.assertRaisesRegex(ConfigError, "unset"):
            resolve_notification_settings(config, environ={})

        webhook_url, secret = resolve_notification_settings(
            config,
            environ={
                "SENTINEL_WEBHOOK_URL": self.base,
                "SENTINEL_WEBHOOK_SECRET": "from-environment",
            },
        )
        self.assertEqual(webhook_url, self.base)
        self.assertEqual(secret, "from-environment")


if __name__ == "__main__":
    unittest.main()
