import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiContractTests(unittest.TestCase):
    def test_ui_references_real_api(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/status", javascript)
        self.assertIn("/api/config", javascript)
        self.assertIn("/api/trends?days=7", javascript)
        self.assertIn("/api/certificates", javascript)
        self.assertIn("check_history", javascript)
        self.assertIn("REFRESH_MS = 10_000", javascript)
        self.assertIn("renderAutomation", javascript)
        self.assertIn("renderLongTrend", javascript)
        self.assertIn("renderCertificates", javascript)

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

    def test_certificate_calendar_renders_truthful_states(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function formatDays", javascript)
        # Missing evidence must render as "--", never as "expired".
        self.assertIn('typeof value !== "number"', javascript)
        self.assertIn("certificate-empty", javascript)
        self.assertIn("还没有 TLS 检查返回证书指标", javascript)
        self.assertIn("renderCertificates", javascript)
        self.assertIn("certificateGrades", javascript)
        self.assertIn('id="certificate-nearest"', html)
        self.assertIn('id="certificate-counts"', html)
        self.assertIn('id="certificate-tracked"', html)

    def test_retention_panel_surfaces_history_bounds(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function formatBytes", javascript)
        self.assertIn("function renderRetention", javascript)
        self.assertIn("automation.retention", javascript)
        self.assertIn("已截断", javascript)
        self.assertIn('id="retention-state"', html)
        self.assertIn('id="retention-usage"', html)
        self.assertIn('id="retention-archives"', html)
        self.assertIn('id="retention-note"', html)

    def test_maintenance_panel_surfaces_window_state(self):
        javascript = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function renderMaintenance", javascript)
        self.assertIn("automation?.maintenance", javascript)
        self.assertIn("active_check_ids", javascript)
        self.assertIn("维护中", javascript)
        self.assertIn('id="maintenance-panel"', html)
        self.assertIn('id="maintenance-state"', html)
        self.assertIn('id="maintenance-list"', html)

    def test_document_has_accessibility_hooks(self):
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="zh-CN"', html)
        self.assertIn("aria-live", html)
        self.assertIn('id="check-search"', html)
        self.assertIn('id="transition-list"', html)
        self.assertIn('id="automation-panel"', html)
        self.assertIn('id="alert-list"', html)
        self.assertIn('id="long-trend-panel"', html)
        self.assertIn('id="long-trend-list"', html)
        self.assertIn('id="certificate-panel"', html)
        self.assertIn('id="certificate-list"', html)
        self.assertIn('id="maintenance-panel"', html)
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

    def test_landing_page_covers_demo_install_and_local_download(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        landing = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('id="demo"', landing)
        self.assertIn('id="install"', landing)
        self.assertIn("/api/alerts", landing)
        self.assertIn("start-sentinel.cmd", landing)
        self.assertIn(f"downloads/sentinel-{version}.zip", landing)
        self.assertIn(f"docs/downloads/sentinel-{version}.zip", readme)

        downloads = ROOT / "docs" / "downloads"
        artifact = downloads / f"sentinel-{version}.zip"
        checksum = downloads / f"sentinel-{version}.zip.sha256"
        if downloads.exists():
            self.assertTrue(artifact.is_file(), artifact)
            self.assertTrue(checksum.is_file(), checksum)

    def test_architecture_doc_covers_layers_and_links_roadmap(self):
        architecture = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for layer in (
            "基础设施与进程模型",
            "网络探测内核",
            "安全与访问控制",
            "云原生",
            "中间件与告警出口",
            "数据与存储",
        ):
            self.assertIn(layer, architecture)
        # Gaps are referenced by id so roadmap items stay traceable to evidence.
        for gap in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
            self.assertIn(gap, architecture)
            self.assertIn(gap, roadmap)
        self.assertIn("docs/ARCHITECTURE.md", roadmap)
        self.assertIn("docs/ARCHITECTURE.md", readme)


if __name__ == "__main__":
    unittest.main()

