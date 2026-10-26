import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from monitor.config import ConfigError, load_config, parse_config


MINIMAL = {
    "version": 1,
    "checks": [
        {
            "id": "api",
            "name": "API",
            "type": "http",
            "target": "https://example.com/health",
        }
    ],
}


class ConfigTests(unittest.TestCase):
    def test_defaults_are_applied(self):
        config = parse_config(MINIMAL)
        check = config.checks[0]
        self.assertEqual(check.expected_status, (200,))
        self.assertEqual(check.timeout_seconds, 5.0)
        self.assertEqual(check.retry_attempts, 0)
        self.assertTrue(check.verify_tls)
        self.assertEqual(check.group, "未分组")
        self.assertEqual(config.thresholds.tls_warn_days, 30)
        self.assertEqual(config.monitor_interval_seconds, 60)
        self.assertFalse(config.notifications.configured)

    def test_group_is_normalized_and_exposed(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"][0]["group"] = "  核心   服务  "
        check = parse_config(raw).checks[0]
        self.assertEqual(check.group, "核心 服务")
        self.assertEqual(check.public_dict()["group"], "核心 服务")

    def test_group_must_be_a_short_non_empty_string(self):
        for value, message in (("   ", "must not be empty"), (42, "must be a string")):
            raw = json.loads(json.dumps(MINIMAL))
            raw["checks"][0]["group"] = value
            with self.assertRaisesRegex(ConfigError, message):
                parse_config(raw)

    def test_domain_defaults_to_network_and_is_exposed(self):
        config = parse_config(MINIMAL)
        check = config.checks[0]
        self.assertEqual(check.domain, "network")
        self.assertEqual(check.public_dict()["domain"], "network")
        self.assertEqual(config.public_dict()["domain_budget"]["default"], 4)

    def test_domain_accepts_known_domains_and_rejects_others(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"][0]["domain"] = "host"
        self.assertEqual(parse_config(raw).checks[0].domain, "host")

        for value in ("gopher", "Network", 7, ""):
            raw = json.loads(json.dumps(MINIMAL))
            raw["checks"][0]["domain"] = value
            with self.assertRaisesRegex(ConfigError, "must be one of"):
                parse_config(raw)

    def test_domain_budget_is_bounded_and_public(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["domain_budget"] = {"network": 2, "host": 8}
        config = parse_config(raw)
        self.assertEqual(config.workers_for_domain("network"), 2)
        self.assertEqual(config.workers_for_domain("host"), 8)
        self.assertEqual(config.workers_for_domain("database"), 4)
        public = config.public_dict()["domain_budget"]
        self.assertEqual(public["network"], 2)
        self.assertEqual(public["host"], 8)
        self.assertEqual(public["default"], 4)

    def test_domain_budget_rejects_unknown_domain_and_bad_values(self):
        for value, message in (
            ({"nope": 2}, "must be one of"),
            ({"network": 0}, "between 1 and 8"),
            ({"network": 9}, "between 1 and 8"),
            ({"network": True}, "must be an integer"),
            ({"network": "2"}, "must be an integer"),
            ([], "must be an object"),
        ):
            raw = json.loads(json.dumps(MINIMAL))
            raw["domain_budget"] = value
            with self.assertRaisesRegex(ConfigError, message):
                parse_config(raw)

    def test_retry_attempts_is_bounded_and_public(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"][0]["retry_attempts"] = 2
        check = parse_config(raw).checks[0]
        self.assertEqual(check.retry_attempts, 2)
        self.assertEqual(check.public_dict()["retry_attempts"], 2)

        for value, message in ((-1, "between"), (3, "between"), (True, "integer")):
            raw = json.loads(json.dumps(MINIMAL))
            raw["checks"][0]["retry_attempts"] = value
            with self.assertRaisesRegex(ConfigError, message):
                parse_config(raw)

    def test_notifications_are_validated_and_redacted(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["monitor_interval_seconds"] = 30
        raw["notifications"] = {
            "webhook_url": "https://hooks.example.test/path?token=secret",
            "signing_secret_env": "SENTINEL_WEBHOOK_SECRET",
            "cooldown_seconds": 120,
            "timeout_seconds": 3,
            "retry_attempts": 2,
        }
        config = parse_config(raw)
        public = config.public_dict()

        self.assertEqual(config.monitor_interval_seconds, 30)
        self.assertTrue(config.notifications.configured)
        self.assertTrue(public["notifications"]["configured"])
        self.assertEqual(
            public["notifications"]["signing_secret_env"],
            "SENTINEL_WEBHOOK_SECRET",
        )
        self.assertNotIn("hooks.example.test", json.dumps(public))
        self.assertNotIn("token=secret", json.dumps(public))

    def test_notification_url_sources_are_mutually_exclusive(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["notifications"] = {
            "webhook_url": "http://127.0.0.1:18081/hook",
            "webhook_url_env": "SENTINEL_WEBHOOK_URL",
        }
        with self.assertRaisesRegex(ConfigError, "not both"):
            parse_config(raw)

    def test_notification_url_rejects_credentials(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["notifications"] = {"webhook_url": "https://user:secret@example.test/"}
        with self.assertRaisesRegex(ConfigError, "credentials"):
            parse_config(raw)

    def test_monitor_interval_is_bounded(self):
        for value in (9, 3601):
            raw = json.loads(json.dumps(MINIMAL))
            raw["monitor_interval_seconds"] = value
            with self.assertRaisesRegex(ConfigError, "between"):
                parse_config(raw)

    def test_rejects_duplicate_ids(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"].append(raw["checks"][0])
        with self.assertRaisesRegex(ConfigError, "unique"):
            parse_config(raw)

    def test_rejects_excessive_check_count(self):
        raw = {
            "version": 1,
            "checks": [
                {
                    "id": f"check-{index}",
                    "name": f"Check {index}",
                    "type": "ping",
                    "target": "127.0.0.1",
                }
                for index in range(201)
            ],
        }
        with self.assertRaisesRegex(ConfigError, "at most 200"):
            parse_config(raw)

    def test_rejects_credentials_in_http_url(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"][0]["target"] = "https://user:secret@example.com/"
        with self.assertRaisesRegex(ConfigError, "credentials"):
            parse_config(raw)

    def test_rejects_unsafe_check_id(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"][0]["id"] = "api; rm -rf /"
        with self.assertRaisesRegex(ConfigError, "may only contain"):
            parse_config(raw)

    def test_tcp_requires_port(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"][0].update({"type": "tcp", "target": "127.0.0.1"})
        with self.assertRaisesRegex(ConfigError, "port is required"):
            parse_config(raw)

    def test_rejects_non_host_target(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"][0].update({"type": "ping", "target": "-f --flood"})
        with self.assertRaisesRegex(ConfigError, "valid hostname"):
            parse_config(raw)

    def test_threshold_order_is_enforced(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["thresholds"] = {"latency_warn_ms": 1000, "latency_fail_ms": 500}
        with self.assertRaisesRegex(ConfigError, "lower"):
            parse_config(raw)

    def test_load_error_mentions_json_position(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"version": 1,}', encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "line"):
                load_config(path)

    def test_missing_file_is_reported(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ConfigError, "not found"):
                load_config(Path(directory) / "missing.json")


if __name__ == "__main__":
    unittest.main()

