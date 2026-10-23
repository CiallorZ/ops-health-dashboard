import unittest
from datetime import datetime, timedelta, timezone

from monitor.certificates import (
    MAX_CERTIFICATE_UPCOMING,
    UPCOMING_WINDOW_DAYS,
    summarize_certificates,
)


def certificate_check(check_id, remaining_days, *, name=None, common_name="", verify=True):
    now = datetime.now(timezone.utc)
    return {
        "id": check_id,
        "name": name or check_id,
        "type": "tls",
        "target": f"{check_id}.example.test",
        "port": 443,
        "status": "ok",
        "group": "外部依赖",
        "metrics": {
            "remaining_days": remaining_days,
            "expires_at": (now + timedelta(days=remaining_days))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "common_name": common_name,
            "verify_tls": verify,
        },
    }


class CertificateCalendarTests(unittest.TestCase):
    def test_grades_and_sorts_upcoming_certificates(self):
        checks = [
            certificate_check("long", 300, name="长期证书"),
            certificate_check("expired", -2, name="已过期证书"),
            certificate_check("critical", 3, name="紧急证书"),
            certificate_check("warning", 12, name="预警证书"),
            certificate_check("fresh", 60, name="新证书"),
        ]
        calendar = summarize_certificates(
            checks, tls_warn_days=30, tls_fail_days=7
        )

        self.assertEqual(calendar["tracked"], 5)
        self.assertEqual(calendar["counts"]["expired"], 1)
        self.assertEqual(calendar["counts"]["critical"], 2)
        self.assertEqual(calendar["counts"]["warning"], 1)
        self.assertEqual(calendar["counts"]["healthy"], 2)
        self.assertEqual(calendar["nearest_remaining_days"], -2.0)
        self.assertEqual(
            [item["check_id"] for item in calendar["upcoming"]],
            ["expired", "critical", "warning", "fresh"],
        )
        self.assertTrue(calendar["upcoming"][0]["remaining_days"] <= 0)
        self.assertEqual(calendar["upcoming"][1]["grade"], "critical")
        self.assertEqual(calendar["upcoming"][2]["grade"], "warning")
        self.assertIsNotNone(calendar["upcoming"][0]["expires_at"])

    def test_checks_without_certificate_metrics_are_ignored(self):
        checks = [
            {"id": "http", "name": "HTTP", "type": "http", "metrics": {"status_code": 200}},
            {
                "id": "failed-tls",
                "name": "失败 TLS",
                "type": "tls",
                "status": "fail",
                "metrics": {},
            },
            {"id": "broken", "name": "坏数据", "metrics": {"remaining_days": "soon"}},
            {"id": "nan", "name": "NaN", "metrics": {"remaining_days": float("nan")}},
        ]
        calendar = summarize_certificates(
            checks, tls_warn_days=30, tls_fail_days=7
        )
        self.assertEqual(calendar["tracked"], 0)
        self.assertEqual(calendar["upcoming"], [])
        self.assertIsNone(calendar["nearest_remaining_days"])

    def test_upcoming_list_is_bounded(self):
        checks = [
            certificate_check(f"cert-{index}", 1 + index) for index in range(30)
        ]
        calendar = summarize_certificates(
            checks, tls_warn_days=30, tls_fail_days=7
        )
        self.assertEqual(len(calendar["upcoming"]), MAX_CERTIFICATE_UPCOMING)
        days = [item["remaining_days"] for item in calendar["upcoming"]]
        self.assertEqual(days, sorted(days))

    def test_remaining_days_follow_the_measured_expiry_not_a_stale_value(self):
        stale = certificate_check("stale", 1)
        stale["metrics"]["remaining_days"] = 999.0
        calendar = summarize_certificates(
            [stale], tls_warn_days=30, tls_fail_days=7
        )
        entry = calendar["upcoming"][0]
        self.assertAlmostEqual(entry["remaining_days"], 1.0, places=1)
        self.assertEqual(entry["grade"], "critical")

    def test_window_only_shows_certificates_inside_the_upcoming_horizon(self):
        checks = [certificate_check("far", UPCOMING_WINDOW_DAYS + 30)]
        calendar = summarize_certificates(
            checks, tls_warn_days=30, tls_fail_days=7
        )
        self.assertEqual(calendar["tracked"], 1)
        self.assertEqual(calendar["upcoming"], [])
        self.assertEqual(calendar["counts"]["healthy"], 1)

    def test_unverified_chain_is_labeled(self):
        calendar = summarize_certificates(
            [certificate_check("self-signed", 5, common_name="self.example", verify=False)],
            tls_warn_days=30,
            tls_fail_days=7,
        )
        self.assertFalse(calendar["upcoming"][0]["verified"])
        self.assertEqual(calendar["upcoming"][0]["common_name"], "self.example")

    def test_limit_is_clamped(self):
        checks = [certificate_check(f"cert-{index}", 1 + index) for index in range(20)]
        calendar = summarize_certificates(
            checks, tls_warn_days=30, tls_fail_days=7, limit=999
        )
        self.assertEqual(len(calendar["upcoming"]), MAX_CERTIFICATE_UPCOMING)

    def test_thresholds_are_echoed_for_the_ui(self):
        calendar = summarize_certificates(
            [], tls_warn_days=21, tls_fail_days=3
        )
        self.assertEqual(
            calendar["thresholds"], {"tls_warn_days": 21.0, "tls_fail_days": 3.0}
        )
        self.assertTrue(calendar["generated_at"].endswith("Z"))

    def test_explicit_reference_time_is_respected(self):
        check = {
            "id": "fixed",
            "name": "Fixed",
            "metrics": {
                "remaining_days": 0,
                "expires_at": "2026-11-20T00:00:00Z",
                "common_name": "",
                "verify_tls": True,
            },
        }
        calendar = summarize_certificates(
            [check],
            tls_warn_days=30,
            tls_fail_days=7,
            now=datetime(2026, 11, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(calendar["upcoming"][0]["remaining_days"], 10.0)
        self.assertEqual(calendar["upcoming"][0]["grade"], "warning")


if __name__ == "__main__":
    unittest.main()
