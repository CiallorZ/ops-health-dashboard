import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from monitor.checks import run_check
from monitor.config import ConfigError, Thresholds, parse_config
from monitor.history import HistoryStore
from monitor.runner import CheckRunnerService


def config_for(path, assertions=None):
    check = {"id": "disk", "name": "Local disk", "type": "disk", "target": str(path)}
    if assertions is not None:
        check["assertions"] = assertions
    return parse_config({"version": 1, "checks": [check]})


class DiskCheckTests(unittest.TestCase):
    def test_validates_absolute_path_and_host_domain(self):
        with TemporaryDirectory() as directory:
            check = config_for(directory).checks[0]
            self.assertEqual(check.domain, "host")
            self.assertEqual(check.public_dict()["target"], directory)
        for target in ("relative", "//server/share", "\\\\server\\share", "\0"):
            with self.subTest(target=target), self.assertRaises(ConfigError):
                config_for(target)
        raw = {"version": 1, "checks": [{"id": "d", "name": "d", "type": "disk",
               "target": str(Path.cwd()), "domain": "network"}]}
        with self.assertRaisesRegex(ConfigError, "must be host"):
            parse_config(raw)

    def test_actual_disk_is_measured_without_claiming_health(self):
        with TemporaryDirectory() as directory:
            result = run_check(config_for(directory).checks[0], Thresholds())
        self.assertEqual(result.status, "unknown")
        self.assertIsNone(result.latency_ms)
        self.assertGreater(result.metrics["total_bytes"], 0)
        self.assertGreaterEqual(result.metrics["free_percent"], 0)
        self.assertLessEqual(result.metrics["free_percent"], 100)
        self.assertIn("未配置容量断言", result.detail)

    def test_assertion_history_and_metrics_share_real_observation(self):
        with TemporaryDirectory() as directory:
            config = config_for(directory, [{"metric": "free_percent", "op": "<", "fail": 101}])
            runner = CheckRunnerService(config, HistoryStore(directory), cache_seconds=0)
            snapshot = runner.get_snapshot(force=True)
            result = snapshot["checks"][0]
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["assertions"][0]["actual"], result["metrics"]["free_percent"])
            expected = {key: result["metrics"][key] for key in (
                "total_bytes", "used_bytes", "free_bytes", "free_percent"
            )}
            self.assertEqual(snapshot["history"][-1]["checks"][0]["metrics"], expected)
            self.assertIn('sentinel_disk_free_bytes{domain="host",id="disk"}', runner.metrics_payload())

    def test_timeout_failure_and_invalid_output_are_bounded(self):
        with TemporaryDirectory() as directory:
            check = config_for(directory).checks[0]
            missing = config_for(Path(directory) / "missing").checks[0]
            self.assertEqual(run_check(missing, Thresholds()).status, "fail")
            with patch("monitor.checks.subprocess.run", side_effect=subprocess.TimeoutExpired("disk", 1)):
                self.assertIn("超时", run_check(check, Thresholds()).detail)
            for output, code in ((b"not json", 0), (json.dumps([0, 0, 0]).encode(), 0), (b"", 1)):
                with self.subTest(output=output), patch("monitor.checks.subprocess.run") as run:
                    run.return_value = subprocess.CompletedProcess([], code, output)
                    result = run_check(check, Thresholds())
                    self.assertEqual(result.status, "fail")
                    self.assertEqual(result.metrics, {})


if __name__ == "__main__":
    unittest.main()
