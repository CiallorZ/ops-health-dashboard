import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiContractTests(unittest.TestCase):
    def test_ui_references_real_api(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/status", javascript)
        self.assertIn("/api/config", javascript)
        self.assertIn("check_history", javascript)
        self.assertIn("REFRESH_MS = 30_000", javascript)

    def test_ui_escapes_remote_text(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function escapeHtml", javascript)
        self.assertIn("escapeHtml(check.name)", javascript)
        self.assertIn("check.group", javascript)
        self.assertIn("check-group-title", javascript)
        self.assertIn("recovered_after_retry", javascript)
        self.assertIn("heartbeat-strip", javascript)
        self.assertIn("check.tags", javascript)
        self.assertIn("renderTransitions", javascript)

    def test_document_has_accessibility_hooks(self):
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="zh-CN"', html)
        self.assertIn("aria-live", html)
        self.assertIn('id="check-search"', html)
        self.assertIn('id="transition-list"', html)
        self.assertIn("prefers-reduced-motion", (ROOT / "dashboard" / "styles.css").read_text(encoding="utf-8"))

    def test_current_version_is_consistent(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        dashboard = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        landing = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        package = (ROOT / "monitor" / "__init__.py").read_text(encoding="utf-8")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"v{version}", dashboard)
        self.assertIn(f"v{version}", readme)
        self.assertIn(f"v{version}", landing)
        self.assertIn(f'__version__ = "{version}"', package)
        self.assertIn(f"## [{version}]", changelog)


if __name__ == "__main__":
    unittest.main()

