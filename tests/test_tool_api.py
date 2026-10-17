import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from server import build_server


class ToolApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        dashboard = root / "dashboard"
        dashboard.mkdir()
        (dashboard / "index.html").write_text("<h1>toolbox</h1>", encoding="utf-8")
        config = root / "checks.json"
        config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "checks": [
                        {
                            "id": "self",
                            "name": "Self",
                            "type": "ping",
                            "target": "127.0.0.1",
                            "timeout_seconds": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            config_path=config,
            data_dir=root / "data",
            dashboard_dir=dashboard,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request_json(self, path, *, method="GET", body=None, content_type=None):
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = content_type or "application/json"
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    def request_error(self, path, *, method="POST", body=None, content_type=None):
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = content_type or "application/json"
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            try:
                self.error_body = json.loads(exc.read())
                return exc.code
            finally:
                exc.close()
        self.fail("request unexpectedly succeeded")

    def test_tool_catalog(self):
        status, body = self.request_json("/api/tools")
        self.assertEqual(status, 200)
        ids = {tool["id"] for tool in body["tools"]}
        self.assertEqual(ids, {"json-format", "cidr", "hash", "ip"})

    def test_cidr_execution(self):
        status, body = self.request_json(
            "/api/tools/run",
            method="POST",
            body={"tool": "cidr", "inputs": {"cidr": "10.0.0.0/30"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["usable_host_count"], 2)

    def test_hash_execution(self):
        status, body = self.request_json(
            "/api/tools/run",
            method="POST",
            body={"tool": "hash", "inputs": {"text": "hello", "algorithm": "sha256"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            body["result"]["digest"],
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        )

    def test_browser_only_json_tool_is_rejected(self):
        code = self.request_error(
            "/api/tools/run",
            body={"tool": "json-format", "inputs": {"text": "{}"}},
        )
        self.assertEqual(code, 400)
        self.assertIn("浏览器本地", self.error_body["error"]["message"])

    def test_unknown_tool_is_400(self):
        code = self.request_error(
            "/api/tools/run",
            body={"tool": "unknown", "inputs": {}},
        )
        self.assertEqual(code, 400)

    def test_oversized_body_is_413(self):
        request = urllib.request.Request(
            self.base + "/api/tools/run",
            data=b"x" * (64 * 1024 + 1),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 413)
        raised.exception.close()

    def test_unknown_input_is_400(self):
        code = self.request_error(
            "/api/tools/run",
            body={"tool": "cidr", "inputs": {"cidr": "10.0.0.0/30", "extra": "x"}},
        )
        self.assertEqual(code, 400)
        self.assertIn("不支持的参数", self.error_body["error"]["message"])

    def test_content_type_is_required(self):
        request = urllib.request.Request(
            self.base + "/api/tools/run",
            data=b'{"tool":"cidr","inputs":{"cidr":"10.0.0.0/30"}}',
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 415)
        raised.exception.close()

    def test_malformed_json_is_400(self):
        request = urllib.request.Request(
            self.base + "/api/tools/run",
            data=b"{",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 400)
        raised.exception.close()


if __name__ == "__main__":
    unittest.main()
