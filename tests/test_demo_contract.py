import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DemoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.external_resources = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag in {"script", "link", "img"}:
            url = attrs.get("src", attrs.get("href", ""))
            if url.startswith(("http:", "https:", "//")):
                self.external_resources.append(url)


class DemoContractTests(unittest.TestCase):
    def test_demo_is_isolated_and_has_accessible_controls(self):
        parser = DemoParser()
        parser.feed((ROOT / "demo" / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        self.assertEqual(parser.external_resources, [])
        for item in ("command-dialog", "command-input", "command-results", "health-chart", "add-form"):
            self.assertIn(item, parser.ids)
        html = (ROOT / "demo" / "index.html").read_text(encoding="utf-8")
        self.assertIn("演示模式 · 数据非真实", html)
        self.assertIn("不连接目标", html)


if __name__ == "__main__":
    unittest.main()
