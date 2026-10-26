"""Bounded, declarative assertions over values produced by a probe."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit


MAX_ASSERTIONS = 8
MAX_METRIC_LENGTH = 64
MAX_LITERAL_LENGTH = 256
MAX_IN_VALUES = 16
MAX_EVIDENCE_TEXT = 256
SUPPORTED_OPERATORS = frozenset(
    {"==", "!=", ">", ">=", "<", "<=", "in", "exists", "missing"}
)


class AssertionConfigError(ValueError):
    """Raised when an assertion is malformed or outside the bounded contract."""


@dataclass(frozen=True)
class Assertion:
    metric: str
    op: str
    warn: Any = None
    fail: Any = None

    def public_dict(self) -> dict[str, Any]:
        result = {"metric": self.metric, "op": self.op}
        if self.warn is not None:
            result["warn"] = self.warn
        if self.fail is not None:
            result["fail"] = self.fail
        return result


def _literal(value: Any, *, name: str) -> Any:
    if isinstance(value, str):
        if not value or len(value) > MAX_LITERAL_LENGTH:
            raise AssertionConfigError(
                f"{name} must be a non-empty string of at most "
                f"{MAX_LITERAL_LENGTH} characters"
            )
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    raise AssertionConfigError(f"{name} must be a finite number, boolean, or string")


def _expected(value: Any, *, op: str, name: str) -> Any:
    if op in {"exists", "missing"}:
        if not isinstance(value, bool):
            raise AssertionConfigError(f"{name} must be a boolean for {op}")
        return value
    if op == "in" and isinstance(value, list):
        if not 1 <= len(value) <= MAX_IN_VALUES:
            raise AssertionConfigError(
                f"{name} must contain 1 to {MAX_IN_VALUES} values"
            )
        return [
            _literal(item, name=f"{name}[{index}]")
            for index, item in enumerate(value)
        ]
    return _literal(value, name=name)


def parse_assertions(raw: Any, *, name: str = "assertions") -> tuple[Assertion, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > MAX_ASSERTIONS:
        raise AssertionConfigError(
            f"{name} must be a list with at most {MAX_ASSERTIONS} entries"
        )
    parsed = []
    for index, item in enumerate(raw):
        label = f"{name}[{index}]"
        if not isinstance(item, dict):
            raise AssertionConfigError(f"{label} must be an object")
        metric = item.get("metric")
        if (
            not isinstance(metric, str)
            or not metric
            or len(metric) > MAX_METRIC_LENGTH
            or not all(char.isalnum() or char in "_-" for char in metric)
        ):
            raise AssertionConfigError(
                f"{label}.metric must be a short metric name using letters, "
                "digits, '_' or '-'"
            )
        op = item.get("op")
        if not isinstance(op, str) or op not in SUPPORTED_OPERATORS:
            supported = ", ".join(sorted(SUPPORTED_OPERATORS))
            raise AssertionConfigError(f"{label}.op must be one of: {supported}")
        if op in {"exists", "missing"}:
            if item.get("warn") is None and item.get("fail") is None:
                raise AssertionConfigError(f"{label} must enable warn or fail")
        elif item.get("warn") is None and item.get("fail") is None:
            raise AssertionConfigError(f"{label} must define warn or fail")
        parsed.append(
            Assertion(
                metric=metric,
                op=op,
                warn=(
                    _expected(item["warn"], op=op, name=f"{label}.warn")
                    if item.get("warn") is not None
                    else None
                ),
                fail=(
                    _expected(item["fail"], op=op, name=f"{label}.fail")
                    if item.get("fail") is not None
                    else None
                ),
            )
        )
    return tuple(parsed)


def _display(value: Any) -> str:
    if value is None:
        return "--"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:MAX_EVIDENCE_TEXT]


def _safe_actual(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = urlsplit(value)
            if parsed.scheme and parsed.netloc:
                host = parsed.hostname or ""
                if parsed.port:
                    host += f":{parsed.port}"
                value = urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        except ValueError:
            return "[invalid URL]"
        return value[:MAX_EVIDENCE_TEXT]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[unsupported value]"


def _same_type(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool)
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isfinite(actual) and math.isfinite(expected)
    return isinstance(actual, str) and isinstance(expected, str)


def _compare(actual: Any, op: str, expected: Any) -> bool | None:
    if op in {"exists", "missing"}:
        present = actual is not None
        return present if op == "exists" else not present
    if actual is None:
        return None
    if op in {">", ">=", "<", "<="}:
        if (
            isinstance(actual, bool)
            or isinstance(expected, bool)
            or not isinstance(actual, (int, float))
            or not isinstance(expected, (int, float))
            or not math.isfinite(actual)
        ):
            return None
        return {
            ">": actual > expected,
            ">=": actual >= expected,
            "<": actual < expected,
            "<=": actual <= expected,
        }[op]
    if op == "in":
        if isinstance(actual, str) and isinstance(expected, str):
            # String ``in`` deliberately means prefix matching, not regex.
            return actual.startswith(expected)
        if not isinstance(expected, list):
            return None
        matches = [
            actual.startswith(item)
            if isinstance(actual, str) and isinstance(item, str)
            else actual == item
            for item in expected
            if _same_type(actual, item)
        ]
        return any(matches) if matches else None
    if not _same_type(actual, expected):
        return None
    return actual == expected if op == "==" else actual != expected


def evaluate_assertions(
    assertions: tuple[Assertion, ...],
    metrics: dict[str, Any],
    *,
    latency_ms: float | None,
) -> list[dict[str, Any]]:
    """Return real values and verdicts; missing or mismatched data is unknown."""
    evidence = []
    for assertion in assertions:
        actual = (
            latency_ms
            if assertion.metric == "latency_ms"
            else metrics.get(assertion.metric)
        )
        expected = assertion.fail if assertion.fail is not None else assertion.warn
        matched = _compare(actual, assertion.op, expected)
        if assertion.op in {"exists", "missing"}:
            matched = _compare(actual, assertion.op, None)
        verdicts = []
        for level in ("fail", "warn"):
            level_expected = getattr(assertion, level)
            if level_expected is None:
                continue
            if assertion.op in {"exists", "missing"}:
                result = matched if level_expected else False
            else:
                result = _compare(actual, assertion.op, level_expected)
            if result:
                verdicts.append(level)
        if actual is None:
            status = "unknown" if not verdicts else verdicts[0]
            reason = "missing metric"
        elif verdicts:
            status = verdicts[0]
            reason = "matched assertion"
        elif any(
            _compare(actual, assertion.op, value) is None
            for value in (assertion.fail, assertion.warn)
            if value is not None
        ):
            status = "unknown"
            reason = "incompatible metric type"
        else:
            status = "ok"
            reason = "no assertion matched"
        criterion = f"{assertion.metric} {assertion.op}"
        if assertion.op not in {"exists", "missing"}:
            parts = []
            for level in ("warn", "fail"):
                value = getattr(assertion, level)
                if value is not None:
                    parts.append(f"{level}={_display(value)}")
            criterion += " " + " ".join(parts)
        safe_actual = _safe_actual(actual)
        evidence.append(
            {
                "metric": assertion.metric,
                "op": assertion.op,
                "actual": safe_actual,
                "status": status,
                "detail": (
                    f"实测 {_display(safe_actual)} / 判定依据 {criterion} · {reason}"
                ),
            }
        )
    return evidence


def assertion_status(evidence: list[dict[str, Any]], *, fallback: str) -> str:
    if fallback == "fail":
        return "fail"
    for status in ("fail", "unknown", "warn"):
        if any(item["status"] == status for item in evidence):
            return status
    return "ok"
