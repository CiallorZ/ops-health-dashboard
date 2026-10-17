import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiContractTests(unittest.TestCase):
    def test_ui_references_real_api(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/status", javascript)
        self.assertIn("/api/config", javascript)
        self.assertIn("REFRESH_MS = 30_000", javascript)
        self.assertIn("/api/tools/run", javascript)
        self.assertIn("formatJsonLocally", javascript)

    def test_ui_escapes_remote_text(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function escapeHtml", javascript)
        self.assertIn("escapeHtml(check.name)", javascript)

    def test_document_has_accessibility_hooks(self):
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="zh-CN"', html)
        self.assertIn("aria-live", html)
        self.assertIn('role="tablist"', html)
        self.assertIn("prefers-reduced-motion", (ROOT / "dashboard" / "styles.css").read_text(encoding="utf-8"))

    def test_json_tool_stays_browser_only(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn('if (activeTool === "json-format")', javascript)
        self.assertIn("formatJsonLocally(inputs.text)", javascript)

    def test_toolbox_has_responsive_layout(self):
        stylesheet = (ROOT / "dashboard" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".toolbox-panel", stylesheet)
        self.assertIn(".tool-layout", stylesheet)
        self.assertIn(".tool-output-error", stylesheet)
        self.assertIn("grid-template-columns: 1fr;\n  }\n\n  .tool-output", stylesheet)


if __name__ == "__main__":
    unittest.main()

