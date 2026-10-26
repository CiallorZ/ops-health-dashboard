import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from monitor.history import (
    LATENCY_BUCKETS,
    MAX_TREND_DAYS,
    HistoryStore,
    summarize_check_history,
    summarize_history_trends,
)


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
        self.assertEqual(api["counts"], {"ok": 1, "warn": 1, "fail": 1, "unknown": 0})
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


class HistoryTrendTests(unittest.TestCase):
    def test_daily_rollups_report_availability_and_percentiles(self):
        checks = [{"id": "api", "name": "API"}]
        history = []
        for index, latency in enumerate((5.0, 30.0, 60.0, 120.0, 900.0, 2500.0), start=1):
            history.append(
                {
                    "run_id": f"run-{index}",
                    "generated_at": f"2026-10-21T00:00:{index:02d}Z",
                    "checks": [
                        {
                            "id": "api",
                            "status": "fail" if index == 6 else "ok",
                            "latency_ms": latency,
                        }
                    ],
                }
            )

        trends = summarize_history_trends(history, checks, days=7)

        day = trends["daily"]["2026-10-21"]
        self.assertEqual(day["samples"], 6)
        self.assertEqual(day["ok"], 5)
        self.assertEqual(day["fail"], 1)
        self.assertEqual(day["availability_percent"], 83.3)
        self.assertEqual(day["latency_samples"], 6)
        self.assertGreaterEqual(day["p50_latency_ms"], 60.0)
        self.assertLessEqual(day["p50_latency_ms"], 120.0)
        self.assertGreaterEqual(day["p95_latency_ms"], 2000.0)
        check = trends["checks"]["api"]
        self.assertEqual(check["days_with_data"], 1)
        self.assertEqual(check["totals"]["fail"], 1)

    def test_missing_days_are_not_invented_and_window_is_bounded(self):
        checks = [{"id": "api", "name": "API"}]
        history = [
            {
                "run_id": "old",
                "generated_at": "2026-09-29T23:00:00Z",
                "checks": [{"id": "api", "status": "ok", "latency_ms": 10}],
            },
            {
                "run_id": "new",
                "generated_at": "2026-10-21T01:00:00Z",
                "checks": [{"id": "api", "status": "fail", "latency_ms": None}],
            },
        ]

        trends = summarize_history_trends(history, checks, days=7)

        self.assertEqual(trends["days"], 7)
        self.assertEqual(trends["days_with_data"], 2)
        self.assertEqual(
            list(trends["daily"]),
            ["2026-10-21", "2026-09-29"],
        )
        self.assertNotIn("2026-10-20", trends["daily"])
        self.assertIsNone(trends["daily"]["2026-10-21"]["p50_latency_ms"])
        self.assertEqual(trends["daily"]["2026-10-21"]["latency_samples"], 0)

        clamped = summarize_history_trends(history, checks, days=999)
        self.assertEqual(clamped["days"], MAX_TREND_DAYS)

    def test_invalid_history_rows_are_ignored(self):
        trends = summarize_history_trends(
            [
                {"generated_at": "not-a-date", "checks": []},
                {"generated_at": "2026-13-45T00:00:00Z", "checks": []},
                {"generated_at": "2026-10-21T00:00:00Z", "checks": "broken"},
                {
                    "generated_at": "2026-10-21T00:00:00Z",
                    "checks": [{"id": "api", "status": "invalid"}],
                },
            ],
            [{"id": "api", "name": "API"}],
        )
        self.assertEqual(trends["checks"], {})
        self.assertEqual(trends["daily"], {})
        self.assertEqual(trends["days_with_data"], 0)

    def test_percentiles_cover_all_latency_buckets(self):
        latencies = (1.0, *LATENCY_BUCKETS, 5000.0)
        history = [
            {
                "generated_at": f"2026-10-21T00:00:{index:02d}Z",
                "checks": [
                    {"id": "api", "status": "ok", "latency_ms": latency},
                ],
            }
            for index, latency in enumerate(latencies, start=1)
        ]

        trends = summarize_history_trends(history, [{"id": "api", "name": "API"}])
        day = trends["daily"]["2026-10-21"]

        self.assertEqual(day["latency_samples"], len(LATENCY_BUCKETS) + 2)
        self.assertIsNotNone(day["p50_latency_ms"])
        self.assertGreaterEqual(day["p95_latency_ms"], day["p50_latency_ms"])
        self.assertGreaterEqual(day["p95_latency_ms"], LATENCY_BUCKETS[-1])


class HistoryRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.data_dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def item(index, checks=None):
        return {
            "run_id": f"run-{index}",
            "generated_at": "2026-10-21T00:00:00Z",
            "checks": checks if checks is not None else [
                {"id": "api", "status": "ok", "latency_ms": 12},
            ],
        }

    def test_append_keeps_history_readable_and_reports_stats(self):
        store = HistoryStore(self.data_dir, max_memory=10)
        store.append(self.item(1))
        store.append(self.item(2))

        self.assertEqual(len(store.recent(10)), 2)
        stats = store.stats()
        self.assertEqual(stats["current_bytes"], (self.data_dir / "history.jsonl").stat().st_size)
        self.assertEqual(stats["archives"], [])
        self.assertEqual(stats["max_archive_files"], 2)
        self.assertFalse(stats["truncated"])
        self.assertGreater(stats["max_total_bytes"], stats["max_file_bytes"])

    def test_rotation_moves_old_runs_into_a_bounded_archive_chain(self):
        store = HistoryStore(
            self.data_dir,
            max_memory=50,
            max_file_bytes=300,
            max_archive_files=2,
        )
        for index in range(12):
            store.append(self.item(index))

        current = self.data_dir / "history.jsonl"
        self.assertLessEqual(current.stat().st_size, store.max_file_bytes)
        archives = sorted(self.data_dir.glob("history.*.jsonl"))
        self.assertLessEqual(len(archives), 2)
        self.assertTrue((self.data_dir / "history.1.jsonl").is_file())
        for archive in archives:
            self.assertLessEqual(archive.stat().st_size, store.max_file_bytes)
        stats = store.stats()
        self.assertLessEqual(stats["total_bytes"], stats["max_total_bytes"])
        self.assertEqual(
            [entry["name"] for entry in stats["archives"]],
            [path.name for path in sorted(self.data_dir.glob("history.[0-9].jsonl"))],
        )

    def test_reload_continues_from_archives_after_rotation(self):
        store = HistoryStore(
            self.data_dir,
            max_memory=200,
            max_file_bytes=260,
            max_archive_files=2,
        )
        for index in range(10):
            store.append(self.item(index))

        reloaded = HistoryStore(
            self.data_dir,
            max_memory=200,
            max_file_bytes=260,
            max_archive_files=2,
        )
        run_ids = [item["run_id"] for item in reloaded.recent(200)]
        self.assertIn("run-9", run_ids)
        self.assertEqual(len(run_ids), len(set(run_ids)))
        self.assertGreaterEqual(len(run_ids), 2)

    def test_dropping_the_oldest_archive_is_reported_as_truncation(self):
        store = HistoryStore(
            self.data_dir,
            max_memory=500,
            max_file_bytes=1024,
            max_archive_files=1,
        )
        # Enough runs to fill the current file, archive it, and archive again,
        # which necessarily deletes the previous archive.
        for index in range(200):
            store.append(self.item(index))

        archives = sorted(self.data_dir.glob("history.*.jsonl"))
        self.assertEqual([path.name for path in archives], ["history.1.jsonl"])
        self.assertTrue(store.stats()["truncated"])
        self.assertIn(
            "history.1.jsonl", [item["name"] for item in store.stats()["archives"]]
        )

    def test_oversized_startup_file_is_compacted_not_trusted_whole(self):
        path = self.data_dir / "history.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        rows = "".join(
            f'{{"run_id":"run-{index}","generated_at":"2026-10-21T00:00:00Z","padding":"'
            + ("x" * 120)
            + '"}\n'
            for index in range(20)
        )
        path.write_text(rows, encoding="utf-8")
        self.assertGreater(path.stat().st_size, 1024)

        store = HistoryStore(self.data_dir, max_memory=100, max_file_bytes=1024)
        self.assertLessEqual(
            (self.data_dir / "history.jsonl").stat().st_size,
            store.max_file_bytes,
        )
        self.assertTrue(store.stats()["truncated"])
        self.assertTrue(store.recent(100))

    def test_zero_archives_deletes_instead_of_growing(self):
        store = HistoryStore(
            self.data_dir,
            max_memory=50,
            max_file_bytes=200,
            max_archive_files=0,
        )
        for index in range(15):
            store.append(self.item(index))

        self.assertEqual(list(self.data_dir.glob("history.*.jsonl")), [])
        self.assertLess(
            (self.data_dir / "history.jsonl").stat().st_size,
            store.max_file_bytes,
        )

    def test_unreadable_lines_are_skipped_without_breaking_rotation(self):
        path = self.data_dir / "history.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"run_id":"good","generated_at":"2026-10-21T00:00:00Z"}\n'
            "not json at all\n"
            '{"run_id":"good-2","generated_at":"2026-10-21T00:00:01Z"}\n',
            encoding="utf-8",
        )
        store = HistoryStore(self.data_dir, max_memory=10)
        self.assertEqual(
            [item["run_id"] for item in store.recent(10)],
            ["good", "good-2"],
        )


if __name__ == "__main__":
    unittest.main()
