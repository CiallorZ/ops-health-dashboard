"""Validate and summarize an IPv4/IPv6 CIDR network."""

from __future__ import annotations

import ipaddress
from typing import Any

from .errors import ToolError


def calculate_cidr(*, cidr: Any) -> dict[str, Any]:
    if not isinstance(cidr, str) or not cidr.strip():
        raise ToolError("请输入 CIDR，例如 192.168.1.0/24", field="cidr")
    value = cidr.strip()
    if "/" not in value:
        raise ToolError("CIDR 必须包含前缀长度，例如 192.168.1.0/24", field="cidr")
    if len(value) > 64:
        raise ToolError("CIDR 长度超出允许范围", field="cidr")
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ToolError(f"CIDR 格式无效：{exc}", field="cidr") from exc

    capacity = network.num_addresses
    if network.version == 4:
        usable = 0 if network.prefixlen >= 31 else max(0, capacity - 2)
        host_count = capacity
    else:
        usable = capacity
        host_count = capacity

    return {
        "cidr": str(network),
        "version": network.version,
        "private": network.is_private,
        "global": network.is_global,
        "prefix_length": network.prefixlen,
        "network_address": str(network.network_address),
        "broadcast_address": (
            str(network.broadcast_address) if network.version == 4 else None
        ),
        "netmask": str(network.netmask) if network.version == 4 else None,
        "host_count": host_count,
        "usable_host_count": usable,
        "first_host": (
            str(network.network_address + 1)
            if network.version == 4 and usable
            else None
        ),
        "last_host": (
            str(network.broadcast_address - 1)
            if network.version == 4 and usable
            else None
        ),
    }
