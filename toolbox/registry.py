"""Small deterministic registry shared by the API and the UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .cidr import calculate_cidr
from .errors import ToolError
from .hash import calculate_hash
from .ip import analyze_ip

ToolHandler = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    id: str
    name: str
    category: str
    description: str
    handler: ToolHandler
    input_schema: dict[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "input": self.input_schema,
        }


TOOLS = {
    "json-format": ToolSpec(
        id="json-format",
        name="JSON 格式化",
        category="developer",
        description="在浏览器本地格式化并校验 JSON，内容不会发送到服务器。",
        handler=lambda: {},
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    ),
    "cidr": ToolSpec(
        id="cidr",
        name="CIDR / IP 计算",
        category="network",
        description="离线校验 CIDR 并给出网络地址、掩码和可用主机范围。",
        handler=calculate_cidr,
        input_schema={
            "type": "object",
            "properties": {"cidr": {"type": "string", "example": "192.168.1.0/24"}},
            "required": ["cidr"],
        },
    ),
    "hash": ToolSpec(
        id="hash",
        name="哈希 / HMAC",
        category="security",
        description="计算 MD5、SHA-1、SHA-256、SHA-384、SHA-512 或对应 HMAC。",
        handler=calculate_hash,
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "algorithm": {"type": "string"},
                "encoding": {"type": "string"},
                "key": {"type": "string"},
            },
            "required": ["text"],
        },
    ),
    "ip": ToolSpec(
        id="ip",
        name="IP 地址分析",
        category="network",
        description="离线判断 IPv4/IPv6 地址类别与网络属性。",
        handler=analyze_ip,
        input_schema={
            "type": "object",
            "properties": {"address": {"type": "string"}},
            "required": ["address"],
        },
    ),
}


def list_tools() -> list[dict[str, Any]]:
    return [spec.public_dict() for spec in TOOLS.values()]


def execute_tool(tool_id: str, inputs: Any) -> dict[str, Any]:
    if tool_id == "json-format":
        raise ToolError("JSON 格式化在浏览器本地执行，服务端不接受其内容")
    spec = TOOLS.get(tool_id)
    if spec is None:
        raise ToolError(f"未知工具：{tool_id}", field="tool")
    if not isinstance(inputs, dict):
        raise ToolError("inputs 必须是 JSON 对象", field="inputs")
    required = spec.input_schema.get("required", [])
    missing = [name for name in required if name not in inputs]
    if missing:
        raise ToolError(f"缺少必填参数：{', '.join(missing)}", field=missing[0])
    allowed = set(spec.input_schema.get("properties", {}))
    unexpected = sorted(set(inputs) - allowed)
    if unexpected:
        raise ToolError(f"不支持的参数：{', '.join(unexpected)}", field=unexpected[0])
    return spec.handler(**inputs)
