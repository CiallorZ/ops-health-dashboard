"""Supported cryptographic digests and HMACs."""

from __future__ import annotations

import codecs
import hashlib
import hmac
from typing import Any

from .errors import ToolError

ALGORITHMS = ("md5", "sha1", "sha256", "sha384", "sha512")
MAX_TEXT_CHARS = 1_000_000


def calculate_hash(
    *,
    text: Any,
    algorithm: Any = "sha256",
    encoding: Any = "utf-8",
    key: Any = "",
) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ToolError("text 必须是字符串", field="text")
    if len(text) > MAX_TEXT_CHARS:
        raise ToolError(f"text 不能超过 {MAX_TEXT_CHARS:,} 个字符", field="text")
    if not isinstance(algorithm, str) or algorithm.lower() not in ALGORITHMS:
        raise ToolError(
            f"algorithm 必须是：{', '.join(ALGORITHMS)}",
            field="algorithm",
        )
    if not isinstance(encoding, str) or not encoding:
        raise ToolError("encoding 必须是非空字符串", field="encoding")
    try:
        encoding = codecs.lookup(encoding).name
    except LookupError as exc:
        raise ToolError(f"无法按 {encoding} 编码：未知编码", field="encoding") from exc
    if encoding not in {"utf-8", "gbk", "ascii"}:
        raise ToolError("encoding 只支持：utf-8, gbk, ascii", field="encoding")
    if key is None:
        key = ""
    if not isinstance(key, str):
        raise ToolError("key 必须是字符串", field="key")
    try:
        text_bytes = text.encode(encoding)
        key_bytes = key.encode(encoding)
    except (LookupError, UnicodeEncodeError) as exc:
        raise ToolError(f"无法按 {encoding} 编码：{exc}", field="encoding") from exc

    name = algorithm.lower()
    if key:
        digest = hmac.new(key_bytes, text_bytes, name).hexdigest()
        mode = "hmac"
    else:
        digest = hashlib.new(name, text_bytes).hexdigest()
        mode = "digest"
    return {
        "algorithm": name,
        "mode": mode,
        "encoding": encoding,
        "input_bytes": len(text_bytes),
        "digest": digest,
    }
