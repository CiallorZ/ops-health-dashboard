import ssl
import socket
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from monitor import __version__
from monitor.checks import USER_AGENT
from monitor.checks import PROBES, CheckExecutionError, _run_http, _run_tls, run_check
from monitor.assertions import Assertion
from monitor.config import CheckConfig, Thresholds
from monitor.config import SUPPORTED_TYPES


class FakeResponse:
    def __init__(self, status=200, url="https://example.com/"):
        self.status = status
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self._url

    def read(self, _size):
        return b"x"


class TlsContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def wrap_socket(self, _socket, server_hostname):
        self.server_hostname = server_hostname
        return self

    def getpeercert(self):
        future = datetime.now(timezone.utc) + timedelta(days=2)
        return {
            "notAfter": future.strftime("%b %d %H:%M:%S %Y GMT"),
            "subject": ((("commonName", "example.com"),),),
        }


class ChecksTests(unittest.TestCase):
    def test_assertions_replace_default_verdict_and_persist_evidence(self):
        check = CheckConfig(
            id="http", name="HTTP", type="http", target="https://example.com",
            assertions=(Assertion("status_code", "in", fail=[200]),),
        )
        with patch("urllib.request.urlopen", return_value=FakeResponse(status=200)):
            result = run_check(check, Thresholds())
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.assertions[0]["actual"], 200)
        self.assertIn("实测 200 / 判定依据 status_code in fail=[200]", result.detail)
        self.assertEqual(result.to_dict()["assertions"], result.assertions)

    def test_missing_assertion_metric_is_unknown_and_not_a_success(self):
        check = CheckConfig(
            id="http", name="HTTP", type="http", target="https://example.com",
            assertions=(Assertion("remaining_days", "<", fail=7),),
        )
        with patch("urllib.request.urlopen", return_value=FakeResponse(status=200)):
            result = run_check(check, Thresholds())
        self.assertEqual(result.status, "unknown")
        self.assertIn("实测 --", result.detail)

    def test_probe_failure_remains_failure(self):
        check = CheckConfig(
            id="bad", name="bad", type="http", target="https://example.com",
            assertions=(Assertion("status_code", "==", fail=200),),
        )
        with patch("urllib.request.urlopen", side_effect=CheckExecutionError("连接失败")):
            self.assertEqual(run_check(check, Thresholds()).status, "fail")

    def test_probe_registry_matches_supported_types(self):
        # config.py owns the accepted set; the registry must never drift.
        self.assertEqual(set(PROBES), SUPPORTED_TYPES)
        for probe in PROBES.values():
            self.assertTrue(callable(probe.validate))
            self.assertTrue(callable(probe.run))
            self.assertIn(probe.domain, {"network", "host", "database",
                                         "middleware", "container", "iot",
                                         "security"})
            self.assertIn(probe.kind, {"prober", "reader"})
            if probe.kind == "reader":
                self.assertTrue(probe.requires_secret)

    def test_probe_contract_rejects_invalid_declarations(self):
        from monitor.checks import (
            Probe,
            _run_ping,
            _validate_ping,
            _validate_probe_contract,
        )

        good = Probe(validate=_validate_ping, run=_run_ping, domain="network")
        _validate_probe_contract("ok", good)

        with self.assertRaisesRegex(ValueError, "unsupported domain"):
            _validate_probe_contract(
                "bad-domain",
                Probe(validate=_validate_ping, run=_run_ping, domain="gopher"),
            )
        with self.assertRaisesRegex(ValueError, "invalid kind"):
            _validate_probe_contract(
                "bad-kind",
                Probe(validate=_validate_ping, run=_run_ping, kind="writer"),
            )
        with self.assertRaisesRegex(ValueError, "requires_secret"):
            _validate_probe_contract(
                "bad-reader",
                Probe(validate=_validate_ping, run=_run_ping, kind="reader"),
            )

    def test_check_result_carries_domain(self):
        check = CheckConfig(
            id="db", name="DB", type="tcp", target="127.0.0.1", port=5432,
            domain="database",
        )
        with patch("monitor.checks.socket.create_connection") as connect:
            connect.return_value.__enter__.return_value.getpeername.return_value = (
                "127.0.0.1",
                5432,
            )
            result = PROBES["tcp"].run(check, Thresholds())
        self.assertEqual(result.domain, "database")
        self.assertEqual(result.to_dict()["domain"], "database")

    def test_registry_dispatches_each_type(self):
        http_check = CheckConfig(
            id="api", name="API", type="http", target="https://example.com/"
        )
        with patch("monitor.checks.urllib.request.urlopen", return_value=FakeResponse()):
            self.assertEqual(PROBES["http"].run(http_check, Thresholds()).status, "ok")

    def test_run_check_uses_registry_validate_before_run(self):
        check = CheckConfig(
            id="bad", name="Bad", type="tcp", target="example.com", port=None
        )
        result = run_check(check, Thresholds())
        self.assertEqual(result.status, "fail")
        self.assertIn("端口", result.detail)

    def test_run_check_rejects_unknown_type(self):
        check = CheckConfig(
            id="x", name="X", type="http", target="https://example.com/"
        )
        object.__setattr__(check, "type", "gopher")
        result = run_check(check, Thresholds())
        self.assertEqual(result.status, "fail")
        self.assertIn("不支持的检查类型", result.detail)

    def test_http_redirect_and_expected_status(self):
        check = CheckConfig(
            id="api",
            name="API",
            type="http",
            target="https://example.com/start",
            expected_status=(200,),
        )
        with patch(
            "monitor.checks.urllib.request.urlopen",
            return_value=FakeResponse(status=200, url="https://example.com/final"),
        ):
            result = _run_http(check, Thresholds())
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.metrics["final_url"], "https://example.com/final")

    def test_result_preserves_configured_group(self):
        check = CheckConfig(
            id="api", name="API", type="http", target="https://example.com/", group="核心服务"
        )
        with patch("monitor.checks.urllib.request.urlopen", return_value=FakeResponse()):
            result = _run_http(check, Thresholds())
        self.assertEqual(result.to_dict()["group"], "核心服务")

    def test_http_user_agent_tracks_the_running_version(self):
        check = CheckConfig(
            id="api", name="API", type="http", target="https://example.com/"
        )
        with patch(
            "monitor.checks.urllib.request.urlopen", return_value=FakeResponse()
        ) as urlopen:
            _run_http(check, Thresholds())
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), USER_AGENT)
        self.assertEqual(USER_AGENT, f"ops-health-dashboard/{__version__}")

    def test_http_wrong_status_is_failure(self):
        check = CheckConfig(
            id="api",
            name="API",
            type="http",
            target="https://example.com/",
            expected_status=(200,),
        )
        with patch(
            "monitor.checks.urllib.request.urlopen",
            return_value=FakeResponse(status=503),
        ):
            result = _run_http(check, Thresholds())
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.metrics["status_code"], 503)

    def test_tls_two_days_is_failure(self):
        check = CheckConfig(
            id="cert",
            name="Cert",
            type="tls",
            target="example.com",
            port=443,
        )
        context = TlsContext()
        with patch("monitor.checks.socket.create_connection"), patch(
            "monitor.checks._ssl_context", return_value=context
        ):
            result = _run_tls(check, Thresholds(tls_warn_days=30, tls_fail_days=7))
        self.assertEqual(result.status, "fail")
        self.assertLess(result.metrics["remaining_days"], 7)

    def test_tls_reports_handshake_error(self):
        check = CheckConfig(
            id="cert",
            name="Cert",
            type="tls",
            target="example.com",
            port=443,
        )
        with patch("monitor.checks.socket.create_connection"), patch(
            "monitor.checks._ssl_context", return_value=TlsContext()
        ), patch.object(
            TlsContext,
            "wrap_socket",
            side_effect=ssl.SSLError("bad certificate"),
        ):
            with self.assertRaisesRegex(CheckExecutionError, "TLS"):
                _run_tls(check, Thresholds())


if __name__ == "__main__":
    unittest.main()

