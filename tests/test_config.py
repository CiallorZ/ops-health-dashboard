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

    def test_rejects_duplicate_ids(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["checks"].append(raw["checks"][0])
        with self.assertRaisesRegex(ConfigError, "unique"):
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

