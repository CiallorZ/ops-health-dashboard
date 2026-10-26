import unittest

from monitor.assertions import (
    Assertion,
    AssertionConfigError,
    assertion_status,
    evaluate_assertions,
    parse_assertions,
)


def evaluate(metric, op, expected, actual, **kwargs):
    metrics = {} if actual is None else {metric: actual}
    if kwargs.get("latency_ms") is not None:
        metrics = {}
    return evaluate_assertions(
        (Assertion(metric=metric, op=op, fail=expected),),
        metrics,
        latency_ms=kwargs.get("latency_ms"),
    )[0]


class AssertionEvaluationTests(unittest.TestCase):
    def test_missing_metric_is_unknown_with_real_evidence(self):
        result = evaluate("status_code", "==", 200, None)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["actual"])
        self.assertIn("实测 --", result["detail"])
        self.assertIn("status_code == 200", result["detail"])

    def test_incompatible_types_and_ordered_comparison_are_unknown(self):
        self.assertEqual(evaluate("status_code", "==", 200, "200")["status"], "unknown")
        self.assertEqual(evaluate("common_name", ">", "a", "beta")["status"], "unknown")
        self.assertEqual(evaluate("status_code", ">=", True, 200)["status"], "unknown")
        self.assertEqual(evaluate("status_code", "in", [200], "200")["status"], "unknown")

    def test_numeric_boundaries_and_latency_are_measured(self):
        self.assertEqual(evaluate("status_code", ">=", 200, 200)["status"], "fail")
        self.assertEqual(evaluate("status_code", ">", 200, 200)["status"], "ok")
        self.assertEqual(evaluate("latency_ms", ">=", 100, None, latency_ms=100)["status"], "fail")

    def test_string_membership_is_literal_prefix(self):
        self.assertEqual(evaluate("common_name", "in", "api.", "api.example.test")["status"], "fail")
        self.assertEqual(evaluate("common_name", "in", ".*", "api.example.test")["status"], "ok")
        self.assertEqual(evaluate("common_name", "in", ["api.", "www."], "www.example")["status"], "fail")

    def test_existence_boolean_and_equality_do_not_coerce_types(self):
        self.assertEqual(evaluate("common_name", "exists", True, "")["status"], "fail")
        self.assertEqual(evaluate("common_name", "missing", True, None)["status"], "fail")
        self.assertEqual(evaluate("status_code", "==", True, 1)["status"], "unknown")

    def test_fail_precedes_warn_unknown_and_fallback_failure(self):
        assertions = (
            Assertion("a", "==", warn=1, fail=1),
            Assertion("b", "==", warn=1),
            Assertion("c", "==", fail=1),
        )
        evidence = evaluate_assertions(assertions, {"a": 1, "b": 1}, latency_ms=None)
        self.assertEqual([item["status"] for item in evidence], ["fail", "warn", "unknown"])
        self.assertEqual(assertion_status(evidence, fallback="ok"), "fail")
        self.assertEqual(assertion_status(evidence[1:], fallback="ok"), "unknown")
        self.assertEqual(assertion_status([], fallback="fail"), "fail")


class AssertionConfigTests(unittest.TestCase):
    def test_valid_config_round_trip_and_bounds(self):
        assertions = parse_assertions([
            {"metric": "status_code", "op": "in", "warn": [200, 204]},
            {"metric": "common_name", "op": "exists", "fail": True},
        ])
        self.assertEqual(assertions[0].public_dict()["warn"], [200, 204])
        self.assertEqual(assertions[1].public_dict(), {"metric": "common_name", "op": "exists", "fail": True})
        self.assertEqual(parse_assertions(None), ())
        with self.assertRaisesRegex(AssertionConfigError, "at most 8"):
            parse_assertions([{}] * 9)

    def test_invalid_operator_metric_literal_and_missing_threshold_are_rejected(self):
        invalid = [
            {"metric": "x", "op": "regex", "fail": ".*"},
            {"metric": "a/b", "op": "==", "fail": 1},
            {"metric": "x", "op": "=="},
            {"metric": "x", "op": "==", "fail": float("nan")},
            {"metric": "x", "op": "==", "fail": {"raw": 1}},
            {"metric": "x", "op": "in", "fail": []},
            {"metric": "x", "op": "exists", "fail": 1},
        ]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(AssertionConfigError):
                parse_assertions([item])
