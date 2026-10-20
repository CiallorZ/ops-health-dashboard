import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiContractTests(unittest.TestCase):
    def test_ui_references_real_api(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/status", javascript)
        self.assertIn("/api/config", javascript)
        self.assertIn("REFRESH_MS = 30_000", javascript)

    def test_ui_escapes_remote_text(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function escapeHtml", javascript)
        self.assertIn("escapeHtml(check.name)", javascript)
        self.assertIn("check.group", javascript)
        self.assertIn("check-group-title", javascript)
        self.assertIn("recovered_after_retry", javascript)

    def test_document_has_accessibility_hooks(self):
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="zh-CN"', html)
        self.assertIn("aria-live", html)
        self.assertIn("v0.4.0", html)
        self.assertIn("prefers-reduced-motion", (ROOT / "dashboard" / "styles.css").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

