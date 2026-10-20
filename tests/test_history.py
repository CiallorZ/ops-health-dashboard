import unittest

from monitor.history import summarize_check_history


def history_item(index, checks):
    return {
        "run_id": f"run-{index}",
        "generated_at": f"2026-10-21T00:00:0{index}Z",
        "checks": checks,
    }


class HistoryInsightTests(unittest.TestCase):
    def test_summarizes_availability_latency_and_state_changes(self):
        checks = [
            {"id": "api", "name": "API", "group": "核心服务"},
            {"id": "port", "name": "Port", "group": "基础设施"},
        ]
        history = [
            history_item(
                1,
                [
                    {"id": "api", "status": "ok", "latency_ms": 10},
                    {"id": "port", "status": "fail", "latency_ms": None},
                ],
            ),
            history_item(
                2,
                [
                    {"id": "api", "status": "warn", "latency_ms": 30},
                    {"id": "port", "status": "fail", "latency_ms": 20},
                ],
            ),
            history_item(
                3,
                [
                    {"id": "api", "status": "fail", "latency_ms": 50},
                    {"id": "port", "status": "ok", "latency_ms": 40},
                ],
            ),
        ]

        insight = summarize_check_history(history, checks, limit=40)

        api = insight["checks"]["api"]
        self.assertEqual(api["samples"], 3)
        self.assertEqual(api["availability_percent"], 66.7)
        self.assertEqual(api["average_latency_ms"], 30.0)
        self.assertEqual(api["counts"], {"ok": 1, "warn": 1, "fail": 1})
        self.assertEqual(api["last_change"]["from"], "warn")
        self.assertEqual(api["last_change"]["to"], "fail")
        self.assertEqual(
            [item["status"] for item in api["heartbeats"]],
            ["ok", "warn", "fail"],
        )
        self.assertEqual(insight["events"][0]["check_id"], "port")
        self.assertEqual(insight["events"][0]["name"], "Port")
        self.assertEqual(insight["events"][1]["check_id"], "api")
        self.assertEqual(insight["events"][1]["from"], "warn")

    def test_legacy_rows_without_check_records_are_not_invented(self):
        insight = summarize_check_history(
            [
                {
                    "run_id": "legacy",
                    "generated_at": "2026-10-20T00:00:00Z",
                    "health": "healthy",
                    "total": 1,
                }
            ],
            [{"id": "api", "name": "API"}],
        )
        self.assertEqual(insight["checks"], {})
        self.assertEqual(insight["events"], [])

    def test_invalid_samples_are_ignored_and_events_are_bounded(self):
        checks = [{"id": "api", "name": "API"}]
        history = [
            history_item(
                index,
                [
                    {"id": "api", "status": "ok" if index % 2 else "fail"},
                    {"id": "api", "status": "not-a-status"},
                    {"id": "unknown", "status": "fail"},
                ],
            )
            for index in range(1, 16)
        ]
        history.append(
            history_item(
                16,
                [{"id": "api", "status": "ok", "latency_ms": True}],
            )
        )

        insight = summarize_check_history(history, checks, limit=40)

        self.assertEqual(len(insight["events"]), 8)
        self.assertEqual(insight["checks"]["api"]["samples"], 16)
        self.assertIsNone(insight["checks"]["api"]["heartbeats"][-1]["latency_ms"])


if __name__ == "__main__":
    unittest.main()
