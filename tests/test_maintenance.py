import json
import unittest
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory

from monitor.alerts import AlertDispatcher, AlertStore
from monitor.checks import CheckResult, isoformat, utc_now
from monitor.config import (
    CheckConfig,
    ConfigError,
    DashboardConfig,
    Thresholds,
    parse_config,
)
from monitor.maintenance import (
    MAX_MAINTENANCE_SPAN_DAYS,
    MaintenanceError,
    MaintenanceWindow,
    active_window_for,
    parse_maintenance_windows,
    summarize_maintenance,
)
from monitor.history import HistoryStore
from monitor.runner import CheckRunnerService


MINIMAL = {
    "version": 1,
    "checks": [
        {"id": "api", "name": "API", "type": "ping", "target": "127.0.0.1"},
        {"id": "db", "name": "DB", "type": "ping", "target": "127.0.0.1"},
    ],
}


def window_payload(**overrides):
    starts = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)
    payload = {
        "id": "release-42",
        "name": "发布窗口",
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=2)).isoformat(),
        "check_ids": ["api"],
    }
    payload.update(overrides)
    return payload


class MaintenanceParsingTests(unittest.TestCase):
    def test_empty_config_means_no_maintenance(self):
        self.assertEqual(parse_maintenance_windows(None), ())

    def test_window_is_parsed_and_normalized(self):
        windows = parse_maintenance_windows(
            [window_payload(starts_at="2026-10-21T08:00:00+08:00")]
        )
        self.assertEqual(len(windows), 1)
        window = windows[0]
        self.assertEqual(
            window.starts_at, datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(window.check_ids, ("api",))
        self.assertTrue(window.suppress_alerts)

    def test_window_without_checks_covers_everything(self):
        window = parse_maintenance_windows([window_payload(check_ids=None)])[0]
        self.assertTrue(window.covers("api"))
        self.assertTrue(window.covers("anything-else"))

    def test_rejects_missing_offset_start(self):
        with self.assertRaisesRegex(MaintenanceError, "offset"):
            parse_maintenance_windows(
                [window_payload(starts_at="2026-10-21T00:00:00")]
            )

    def test_rejects_end_not_after_start(self):
        with self.assertRaisesRegex(MaintenanceError, "after starts_at"):
            parse_maintenance_windows(
                [
                    window_payload(
                        starts_at="2026-10-21T02:00:00Z",
                        ends_at="2026-10-21T02:00:00Z",
                    )
                ]
            )

    def test_rejects_overlong_window(self):
        starts = datetime(2026, 10, 21, tzinfo=timezone.utc)
        ends = starts + timedelta(days=MAX_MAINTENANCE_SPAN_DAYS + 1)
        with self.assertRaisesRegex(MaintenanceError, "at most"):
            parse_maintenance_windows(
                [
                    window_payload(
                        starts_at=starts.isoformat(), ends_at=ends.isoformat()
                    )
                ]
            )

    def test_rejects_duplicate_ids_and_too_many_windows(self):
        with self.assertRaisesRegex(MaintenanceError, "unique"):
            parse_maintenance_windows([window_payload(), window_payload()])
        with self.assertRaisesRegex(MaintenanceError, "at most 20"):
            parse_maintenance_windows(
                [window_payload(id=f"w{index}") for index in range(21)]
            )

    def test_rejects_unsafe_id_and_non_boolean_suppression(self):
        with self.assertRaisesRegex(MaintenanceError, "may only contain"):
            parse_maintenance_windows([window_payload(id="a; rm -rf /")])
        with self.assertRaisesRegex(MaintenanceError, "boolean"):
            parse_maintenance_windows([window_payload(suppress_alerts="yes")])


class MaintenanceStateTests(unittest.TestCase):
    def window(self):
        starts = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)
        return MaintenanceWindow(
            id="release-42",
            name="发布窗口",
            starts_at=starts,
            ends_at=starts + timedelta(hours=2),
            check_ids=("api",),
        )

    def test_states_follow_real_clock(self):
        window = self.window()
        before = datetime(2026, 10, 20, 23, 0, tzinfo=timezone.utc)
        during = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)
        after = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(window.state(before), "upcoming")
        self.assertEqual(window.state(during), "active")
        self.assertEqual(window.state(after), "past")
        self.assertEqual(window.public_dict(during)["remaining_seconds"], 3600)

    def test_summary_reports_only_configured_checks(self):
        window = parse_maintenance_windows(
            [window_payload(check_ids=["api", "removed-check"])]
        )[0]
        during = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)
        summary = summarize_maintenance(
            (window,),
            [{"id": "api"}, {"id": "db"}],
            now=during,
        )
        self.assertTrue(summary["configured"])
        self.assertEqual(len(summary["active"]), 1)
        self.assertEqual(summary["active_check_ids"], ["api"])
        self.assertEqual(summary["suppressed_alert_checks"], 1)

    def test_summary_is_empty_outside_the_window(self):
        window = self.window()
        later = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)
        summary = summarize_maintenance((window,), [{"id": "api"}], now=later)
        self.assertEqual(summary["active"], [])
        self.assertEqual(summary["upcoming"], [])
        self.assertEqual(summary["active_check_ids"], [])

    def test_active_window_lookup_respects_check_scope_and_flag(self):
        window = self.window()
        during = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)
        self.assertIsNotNone(active_window_for((window,), "api", now=during))
        self.assertIsNone(active_window_for((window,), "db", now=during))
        muted = MaintenanceWindow(
            id="muted",
            name="只展示",
            starts_at=window.starts_at,
            ends_at=window.ends_at,
            check_ids=(),
            suppress_alerts=False,
        )
        self.assertIsNone(active_window_for((muted,), "api", now=during))


class MaintenanceConfigTests(unittest.TestCase):
    def test_config_exposes_rules_without_time_state(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["maintenance_windows"] = [window_payload()]
        public = parse_config(raw).public_dict()
        self.assertEqual(public["maintenance_windows"][0]["id"], "release-42")
        self.assertEqual(public["maintenance_windows"][0]["check_ids"], ["api"])
        self.assertNotIn("state", public["maintenance_windows"][0])

    def test_unknown_check_ids_are_rejected(self):
        raw = json.loads(json.dumps(MINIMAL))
        raw["maintenance_windows"] = [window_payload(check_ids=["api", "typo"])]
        with self.assertRaisesRegex(ConfigError, "unknown check ids: typo"):
            parse_config(raw)


class MaintenanceSuppressionTests(unittest.TestCase):
    def test_alert_ledger_records_maintenance_suppression(self):
        with TemporaryDirectory() as directory:
            dispatcher = AlertDispatcher(
                "http://127.0.0.1:9/hook",
                signing_secret=None,
                cooldown_seconds=0,
                timeout_seconds=1,
                retry_attempts=0,
                store=AlertStore(directory),
            )
            self.addCleanup(dispatcher.close)
            check = CheckConfig(id="api", name="API", type="ping", target="127.0.0.1")
            result = CheckResult(
                id=check.id,
                name=check.name,
                type=check.type,
                target=check.target,
                port=check.port,
                status="fail",
                summary="down",
                detail="down",
                latency_ms=5.0,
                checked_at=isoformat(utc_now()),
            )
            dispatcher.notify_transition(
                result,
                None,
                {"health": "critical", "total": 1, "ok": 0, "warn": 0, "fail": 1},
                maintenance_name="发布窗口",
            )
            self.assertTrue(dispatcher.wait_for_idle(5))
            record = dispatcher.status()["recent"][0]
        self.assertEqual(record["status"], "suppressed")
        self.assertIn("maintenance window", record["detail"])


class MaintenanceRunnerTests(unittest.TestCase):
    def _config(self):
        now = datetime.now(timezone.utc)
        return DashboardConfig(
            version=1,
            thresholds=Thresholds(),
            checks=(
                CheckConfig(id="api", name="API", type="ping", target="127.0.0.1"),
                CheckConfig(id="db", name="DB", type="ping", target="127.0.0.1"),
            ),
            maintenance_windows=(
                MaintenanceWindow(
                    id="release-42",
                    name="发布窗口",
                    starts_at=now - timedelta(minutes=5),
                    ends_at=now + timedelta(minutes=55),
                    check_ids=("api",),
                ),
            ),
        )

    def test_transition_inside_window_is_suppressed_for_covered_check_only(self):
        calls = []

        class RecordingDispatcher:
            def notify_transition(self, check, previous, _summary, **kwargs):
                calls.append((check.id, kwargs.get("maintenance_name")))

            def status(self, **_kwargs):
                return {"configured": True, "recent": []}

        def failing_check(check, _thresholds):
            return CheckResult(
                id=check.id,
                name=check.name,
                type=check.type,
                target=check.target,
                port=check.port,
                status="fail",
                summary="down",
                detail="down",
                latency_ms=None,
                checked_at=isoformat(utc_now()),
            )

        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                self._config(),
                HistoryStore(directory),
                cache_seconds=0,
                check_runner=failing_check,
                alert_dispatcher=RecordingDispatcher(),
            )
            runner.get_snapshot(force=True)

        self.assertEqual(
            sorted(calls),
            sorted([("api", "发布窗口"), ("db", None)]),
        )

    def test_maintenance_summary_uses_live_clock(self):
        self.assertIsNotNone(self._config())
        with TemporaryDirectory() as directory:
            runner = CheckRunnerService(
                self._config(),
                HistoryStore(directory),
                cache_seconds=60,
                check_runner=lambda check, _thresholds: CheckResult(
                    id=check.id,
                    name=check.name,
                    type=check.type,
                    target=check.target,
                    port=check.port,
                    status="ok",
                    summary="ok",
                    detail="ok",
                    latency_ms=1.0,
                    checked_at=isoformat(utc_now()),
                ),
            )
            runner.get_snapshot(force=True)
            summary = runner.get_maintenance()
        self.assertTrue(summary["configured"])
        self.assertEqual([item["id"] for item in summary["active"]], ["release-42"])
        self.assertEqual(summary["active_check_ids"], ["api"])


if __name__ == "__main__":
    unittest.main()
