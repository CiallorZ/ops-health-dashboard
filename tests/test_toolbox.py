import hashlib
import ipaddress
import unittest

from toolbox.cidr import calculate_cidr
from toolbox.errors import ToolError
from toolbox.hash import calculate_hash
from toolbox.ip import analyze_ip
from toolbox.registry import execute_tool, list_tools


class CidrTests(unittest.TestCase):
    def test_ipv4_summary(self):
        result = calculate_cidr(cidr="192.168.1.10/24")
        self.assertEqual(result["cidr"], "192.168.1.0/24")
        self.assertEqual(result["network_address"], "192.168.1.0")
        self.assertEqual(result["broadcast_address"], "192.168.1.255")
        self.assertEqual(result["host_count"], 256)
        self.assertEqual(result["usable_host_count"], 254)
        self.assertEqual(result["first_host"], "192.168.1.1")
        self.assertTrue(result["private"])

    def test_host_prefix(self):
        result = calculate_cidr(cidr="10.0.0.1/32")
        self.assertEqual(result["usable_host_count"], 0)
        self.assertIsNone(result["first_host"])

    def test_ipv6_summary(self):
        result = calculate_cidr(cidr="2001:db8::/126")
        self.assertEqual(result["version"], 6)
        self.assertIsNone(result["broadcast_address"])
        self.assertEqual(result["usable_host_count"], 4)

    def test_rejects_missing_prefix(self):
        with self.assertRaisesRegex(ToolError, "前缀"):
            calculate_cidr(cidr="192.168.1.1")

    def test_rejects_invalid_input(self):
        with self.assertRaises(ToolError) as raised:
            calculate_cidr(cidr="definitely-not-cidr/24")
        self.assertEqual(raised.exception.field, "cidr")


class HashTests(unittest.TestCase):
    def test_sha256_matches_stdlib(self):
        result = calculate_hash(text="hello", algorithm="sha256")
        self.assertEqual(
            result["digest"],
            hashlib.sha256(b"hello").hexdigest(),
        )
        self.assertEqual(result["mode"], "digest")

    def test_hmac_mode(self):
        result = calculate_hash(text="hello", algorithm="sha256", key="secret")
        self.assertEqual(result["mode"], "hmac")
        self.assertEqual(len(result["digest"]), 64)

    def test_rejects_unknown_algorithm(self):
        with self.assertRaisesRegex(ToolError, "algorithm"):
            calculate_hash(text="hello", algorithm="sha999")

    def test_rejects_invalid_encoding(self):
        with self.assertRaisesRegex(ToolError, "编码"):
            calculate_hash(text="hello", encoding="not-a-codec")

    def test_rejects_unlisted_encoding(self):
        with self.assertRaisesRegex(ToolError, "只支持"):
            calculate_hash(text="hello", encoding="utf-16")

    def test_normalizes_encoding_alias(self):
        result = calculate_hash(text="hello", encoding="UTF8")
        self.assertEqual(result["encoding"], "utf-8")

    def test_size_limit(self):
        with self.assertRaisesRegex(ToolError, "不能超过"):
            calculate_hash(text="x" * 1_000_001)


class IpTests(unittest.TestCase):
    def test_private_ipv4(self):
        result = analyze_ip(address="192.168.1.20")
        self.assertTrue(result["is_private"])
        self.assertFalse(result["is_global"])
        self.assertEqual(result["version"], 4)

    def test_ipv6_loopback(self):
        result = analyze_ip(address="::1")
        self.assertTrue(result["is_loopback"])
        self.assertEqual(result["version"], 6)

    def test_rejects_invalid_address(self):
        with self.assertRaisesRegex(ToolError, "无效"):
            analyze_ip(address="999.1.1.1")

    def test_matches_standard_library(self):
        result = analyze_ip(address="8.8.8.8")
        address = ipaddress.ip_address("8.8.8.8")
        self.assertEqual(result["is_global"], address.is_global)


class RegistryTests(unittest.TestCase):
    def test_metadata_is_unique_and_includes_required_tools(self):
        tools = list_tools()
        ids = [item["id"] for item in tools]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {"json-format", "cidr", "hash", "ip"})

    def test_execute_cidr(self):
        result = execute_tool("cidr", {"cidr": "10.0.0.0/30"})
        self.assertEqual(result["usable_host_count"], 2)

    def test_rejects_unknown_tool(self):
        with self.assertRaisesRegex(ToolError, "未知工具"):
            execute_tool("missing", {})

    def test_rejects_non_object_inputs(self):
        with self.assertRaisesRegex(ToolError, "JSON 对象"):
            execute_tool("cidr", ["192.168.1.1/24"])

    def test_rejects_missing_required_input(self):
        with self.assertRaisesRegex(ToolError, "缺少必填参数"):
            execute_tool("cidr", {})

    def test_rejects_unexpected_input(self):
        with self.assertRaisesRegex(ToolError, "不支持的参数"):
            execute_tool("cidr", {"cidr": "10.0.0.0/30", "command": "whoami"})

    def test_json_tool_never_accepts_server_side_payload(self):
        with self.assertRaisesRegex(ToolError, "浏览器本地"):
            execute_tool("json-format", {"text": "{}"})


if __name__ == "__main__":
    unittest.main()
