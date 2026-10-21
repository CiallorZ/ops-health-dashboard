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
        self.assertEqual(
            second["history"][-1]["checks"],
            [
                {"id": "a", "status": "ok", "latency_ms": 12.5},
                {"id": "b", "status": "ok", "latency_ms": 12.5},
            ],
        )
        self.assertEqual(second["check_history"]["checks"]["a"]["samples"], 2)
        self.assertEqual(
            second["check_history"]["checks"]["a"]["availability_percent"],
            100.0,
        )
        self.assertNotIn("target", second["history"][-1]["checks"][0])

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

    def test_force_refresh_bypasses_cache_window(self):
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                self._config(),
                HistoryStore(directory),
                cache_seconds=60,
                check_runner=fake_check,
            )
            first = runner.get_snapshot(force=True)
            second = runner.get_snapshot(force=True)
            third = runner.get_snapshot()
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(second["run_id"], third["run_id"])

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

    def test_failed_check_retries_and_reports_recovery(self):
        calls = 0

        def flaky_check(check, thresholds):
            nonlocal calls
            calls += 1
            result = fake_check(check, thresholds)
            result.status = "fail" if calls == 1 else "ok"
            return result

        config = DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(
                CheckConfig(
                    id="flaky",
                    name="Flaky",
                    type="ping",
                    target="127.0.0.1",
                    retry_attempts=2,
                ),
            ),
        )
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                config, HistoryStore(directory), cache_seconds=0, check_runner=flaky_check
            )
            snapshot = runner.get_snapshot(force=True)
        result = snapshot["checks"][0]
        self.assertEqual(calls, 2)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metrics"]["attempts"], 2)
        self.assertTrue(result["metrics"]["recovered_after_retry"])

    def test_failed_check_stops_at_configured_retry_limit(self):
        calls = 0

        def failed_check(check, thresholds):
            nonlocal calls
            calls += 1
            result = fake_check(check, thresholds)
            result.status = "fail"
            return result

        config = DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(
                CheckConfig(
                    id="failed",
                    name="Failed",
                    type="ping",
                    target="127.0.0.1",
                    retry_attempts=2,
                ),
            ),
        )
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                config, HistoryStore(directory), cache_seconds=0, check_runner=failed_check
            )
            snapshot = runner.get_snapshot(force=True)
        result = snapshot["checks"][0]
        self.assertEqual(calls, 3)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["metrics"]["attempts"], 3)
        self.assertFalse(result["metrics"]["recovered_after_retry"])

    def test_check_history_tracks_recovery_transition(self):
        calls = 0

        def changing_check(check, thresholds):
            nonlocal calls
            calls += 1
            result = fake_check(check, thresholds)
            result.status = "fail" if calls == 1 else "ok"
            return result

        config = DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(CheckConfig(id="api", name="API", type="ping", target="127.0.0.1"),),
        )
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                config,
                HistoryStore(directory),
                cache_seconds=0,
                check_runner=changing_check,
            )
            first = runner.get_snapshot(force=True)
            second = runner.get_snapshot(force=True)
        self.assertEqual(first["check_history"]["checks"]["api"]["samples"], 1)
        self.assertEqual(second["check_history"]["checks"]["api"]["samples"], 2)
        self.assertEqual(second["check_history"]["events"][0]["from"], "fail")
        self.assertEqual(second["check_history"]["events"][0]["to"], "ok")

    def test_alert_dispatcher_receives_failure_and_recovery_transitions(self):
        statuses = iter(("fail", "ok", "ok", "fail"))

        class RecordingDispatcher:
            def __init__(self):
                self.events = []

            def notify_transition(self, check, previous, _summary, **_kwargs):
                self.events.append((check.status, previous))

            def status(self, **_kwargs):
                return {"configured": True, "recent": []}

        def changing_check(check, thresholds):
            value = next(statuses)
            item = fake_check(check, thresholds)
            item.status = value
            return item

        dispatcher = RecordingDispatcher()
        config = DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(CheckConfig(id="api", name="API", type="ping", target="127.0.0.1"),),
        )
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                config,
                HistoryStore(directory),
                cache_seconds=0,
                check_runner=changing_check,
                alert_dispatcher=dispatcher,
            )
            for _ in range(4):
                runner.get_snapshot(force=True)

        self.assertEqual(
            dispatcher.events,
            [("fail", None), ("ok", "fail"), ("fail", "ok")],
        )


class TrendIntegrationTests(unittest.TestCase):
    def test_snapshot_can_include_bounded_trends(self):
        config = DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(CheckConfig(id="api", name="API", type="ping", target="127.0.0.1"),),
        )
        with TemporaryDirectory() as directory:
            store = HistoryStore(directory)
            store.append(
                {
                    "run_id": "run-1",
                    "generated_at": "2026-10-20T23:59:59Z",
                    "checks": [{"id": "api", "status": "fail", "latency_ms": None}],
                }
            )
            runner = CheckRunnerService(
                config,
                store,
                cache_seconds=60,
                check_runner=fake_check,
            )
            without_trends = runner.get_snapshot(force=True)
            with_trends = runner.get_snapshot(trend_days=7)

        self.assertNotIn("trends", without_trends)
        trends = with_trends["trends"]
        self.assertEqual(trends["days"], 7)
        self.assertEqual(trends["days_with_data"], 2)
        self.assertEqual(trends["daily"]["2026-10-21"]["samples"], 1)
        self.assertEqual(trends["daily"]["2026-10-20"]["availability_percent"], 0.0)
        self.assertIsNone(trends["daily"]["2026-10-20"]["p50_latency_ms"])

    def test_trend_endpoint_route_does_not_reuse_stale_history(self):
        config = DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(CheckConfig(id="api", name="API", type="ping", target="127.0.0.1"),),
        )
        with TemporaryDirectory() as directory:
            store = HistoryStore(directory)
            runner = CheckRunnerService(
                config,
                store,
                cache_seconds=60,
                check_runner=fake_check,
            )
            runner.get_snapshot(force=True)
            store.append(
                {
                    "run_id": "injected",
                    "generated_at": "2026-10-19T00:00:00Z",
                    "checks": [{"id": "api", "status": "warn", "latency_ms": 30.0}],
                }
            )
            trends = runner.get_trends(days=30)

        self.assertEqual(trends["days_with_data"], 2)
        self.assertEqual(list(trends["daily"]), ["2026-10-21", "2026-10-19"])

    def test_metrics_payload_uses_only_allowed_labels(self):
        config = DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(
                CheckConfig(id="a", name="A", type="ping", target="127.0.0.1"),
                CheckConfig(id="b", name="B", type="ping", target="127.0.0.1"),
            ),
        )
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                config,
                HistoryStore(directory),
                cache_seconds=0,
                check_runner=fake_check,
            )
            runner.get_snapshot(force=True)
            payload = runner.metrics_payload()
        lines = payload.splitlines()
        self.assertIn('sentinel_check_up{domain="未分组",id="a"} 1', lines)
        self.assertIn('sentinel_check_up{domain="未分组",id="b"} 1', lines)
        self.assertNotIn("type=", payload)
        up_lines = [line for line in lines if line.startswith("sentinel_check_up{")]
        self.assertEqual(len(up_lines), 2)
        history_lines = [line for line in lines if line.startswith("sentinel_history_")]
        self.assertEqual(len(history_lines), 5)
        self.assertIn("sentinel_history_truncated 0", lines)

    def test_metrics_payload_without_cached_snapshot(self):
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                DashboardConfig(
                    version=1,
                    thresholds=Thresholds(),
                    checks=(
                        CheckConfig(id="a", name="A", type="ping", target="127.0.0.1"),
                        CheckConfig(id="b", name="B", type="ping", target="127.0.0.1"),
                    ),
                ),
                HistoryStore(directory),
                cache_seconds=0,
                check_runner=fake_check,
            )
            payload = runner.metrics_payload()
        self.assertIn("sentinel_history_bytes ", payload)
        self.assertNotIn("sentinel_check_up{", payload)


if __name__ == "__main__":
    unittest.main()

