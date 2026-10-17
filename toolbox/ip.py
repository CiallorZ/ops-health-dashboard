"""Summarize IPv4 and IPv6 addresses without network access."""

from __future__ import annotations

import ipaddress
from typing import Any

from .errors import ToolError


def analyze_ip(*, address: Any) -> dict[str, Any]:
    if not isinstance(address, str) or not address.strip():
        raise ToolError("请输入 IP 地址", field="address")
    value = address.strip()
    if len(value) > 64:
        raise ToolError("IP 地址长度超出允许范围", field="address")
    try:
        ip = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ToolError(f"IP 地址无效：{exc}", field="address") from exc

    return {
        "address": str(ip),
        "version": ip.version,
        "is_private": ip.is_private,
        "is_global": ip.is_global,
        "is_loopback": ip.is_loopback,
        "is_multicast": ip.is_multicast,
        "is_link_local": ip.is_link_local,
        "is_reserved": ip.is_reserved,
        "is_unspecified": ip.is_unspecified,
        "compressed": ip.compressed,
        "exploded": ip.exploded,
    }
