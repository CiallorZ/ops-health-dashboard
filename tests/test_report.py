import unittest

from monitor.report import build_report


class ReportTests(unittest.TestCase):
    def render(self, snapshot):
        return build_report(snapshot, skipped_check_ids=()).decode("utf-8")

    def test_zero_counts_are_rendered_as_zero_not_blank(self):
        body = self.render(
            {
                "generated_at": "2026-10-21T00:00:00Z",
                "summary": {"health": "healthy", "total": 1, "ok": 1, "warn": 0, "fail": 0},
                "checks": [],
            }
        )
        self.assertIn("总计: 1", body)
        self.assertIn("正常: 1", body)
        self.assertIn("预警: 0", body)
        self.assertIn("失败: 0", body)

    def test_retry_recovery_is_visible(self):
        body = self.render(
            {
                "generated_at": "2026-10-21T00:00:00Z",
                "summary": {"health": "healthy", "total": 1, "ok": 1, "warn": 0, "fail": 0},
                "checks": [
                    {
                        "group": "核心服务",
                        "name": "Flaky API",
                        "type": "http",
                        "target": "http://127.0.0.1:18080/health",
                        "status": "ok",
                        "summary": "HTTP 200",
                        "detail": "响应正常",
                        "latency_ms": 12.5,
                        "metrics": {"attempts": 2, "recovered_after_retry": True},
                    }
                ],
            }
        )
        self.assertIn("重试恢复", body)
        self.assertIn(">2（重试恢复）<", body)

    def test_missing_retry_metadata_is_explicit(self):
        body = self.render(
            {
                "generated_at": "2026-10-21T00:00:00Z",
                "summary": {},
                "checks": [
                    {
                        "name": "Legacy",
                        "type": "ping",
                        "target": "127.0.0.1",
                        "status": "ok",
                        "summary": "ICMP 可达",
                        "detail": "主机已回应 ICMP Echo",
                        "latency_ms": 1.0,
                    }
                ],
            }
        )
        self.assertIn("未记录", body)


if __name__ == "__main__":
    unittest.main()
