import threading
import time
import unittest
from tempfile import TemporaryDirectory

from monitor.checks import CheckResult, isoformat, utc_now
from monitor.config import CheckConfig, DashboardConfig, Thresholds
from monitor.history import HistoryStore
from monitor.runner import CheckRunnerService


def fake_check(check, _thresholds):
    return CheckResult(
        id=check.id,
        name=check.name,
        type=check.type,
        target=check.target,
        port=check.port,
        status="ok",
        summary="ok",
        detail="checked",
        latency_ms=12.5,
        checked_at=isoformat(utc_now()),
    )


class RunnerTests(unittest.TestCase):
    def _config(self):
        return DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(
                CheckConfig(id="a", name="A", type="ping", target="127.0.0.1"),
                CheckConfig(id="b", name="B", type="ping", target="127.0.0.1"),
            ),
        )

    def test_snapshot_shape_and_history(self):
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                self._config(),
                HistoryStore(directory),
                cache_seconds=0,
                check_runner=fake_check,
            )
            first = runner.get_snapshot(force=True)
            second = runner.get_snapshot(force=True)
        self.assertEqual(first["summary"]["health"], "healthy")
        self.assertEqual(first["summary"]["ok"], 2)
        self.assertEqual(len(second["history"]), 2)
        self.assertEqual(second["history"][-1]["run_id"], second["run_id"])

    def test_cache_reuses_snapshot(self):
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                self._config(),
                HistoryStore(directory),
                cache_seconds=60,
                check_runner=fake_check,
            )
            first = runner.get_snapshot(force=True)
            second = runner.get_snapshot()
        self.assertEqual(first["run_id"], second["run_id"])

    def test_concurrent_requests_produce_one_refresh(self):
        calls = 0

        def slow_check(check, thresholds):
            nonlocal calls
            calls += 1
            time.sleep(0.08)
            return fake_check(check, thresholds)

        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                self._config(),
                HistoryStore(directory),
                cache_seconds=0,
                check_runner=slow_check,
            )
            results = []
            threads = [
                threading.Thread(target=lambda: results.append(runner.get_snapshot()))
                for _ in range(4)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len({item["run_id"] for item in results}), 1)
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()

