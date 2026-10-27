import json
import subprocess
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from monitor.checks import run_check
from monitor.config import ConfigError, Thresholds, parse_config
from monitor.history import HistoryStore
from monitor.runner import CheckRunnerService


def dns_config(target="localhost", **options):
    return parse_config({"version": 1, "checks": [
        {"id": "dns", "name": "Local resolver", "type": "dns", "target": target, **options}
    ]})


class DnsCheckTests(unittest.TestCase):
    def test_localhost_uses_system_resolver_and_records_real_evidence(self):
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(dns_config(), HistoryStore(directory), cache_seconds=0)
            snapshot = runner.get_snapshot(force=True)
            result = snapshot["checks"][0]
            self.assertIn(result["status"], ("ok", "warn", "fail"))
            self.assertTrue(result["metrics"]["addresses"])
            self.assertEqual(snapshot["history"][-1]["checks"][0]["metrics"], {
                key: result["metrics"][key] for key in ("addresses", "address_count")
            })
            self.assertEqual(result["domain"], "network")

    def test_bad_hostname_is_rejected(self):
        with self.assertRaises(ConfigError):
            dns_config("http://localhost/")
        with self.assertRaises(ConfigError):
            dns_config(port=53)

    def test_timeout_error_and_malformed_child_output(self):
        check = dns_config().checks[0]
        with patch("monitor.checks.subprocess.run", side_effect=subprocess.TimeoutExpired("dns", 1)):
            self.assertIn("超时", run_check(check, Thresholds()).detail)
        for output, code in ((b"", 1), (b"bad", 0), (json.dumps([1, []]).encode(), 0),
                             (json.dumps([1, ["not-an-ip"]]).encode(), 0)):
            with self.subTest(output=output), patch("monitor.checks.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], code, output)
                self.assertEqual(run_check(check, Thresholds()).status, "fail")

    def test_latency_threshold_and_assertion_use_resolver_measurement(self):
        check = dns_config(assertions=[{"metric": "address_count", "op": "<", "fail": 2}]).checks[0]
        output = json.dumps([42.0, ["127.0.0.1"]]).encode()
        with patch("monitor.checks.subprocess.run", return_value=subprocess.CompletedProcess([], 0, output)):
            result = run_check(check, Thresholds())
        self.assertEqual(result.latency_ms, 42.0)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.assertions[0]["actual"], 1)


if __name__ == "__main__":
    unittest.main()
