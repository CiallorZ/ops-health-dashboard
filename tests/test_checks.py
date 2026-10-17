import ssl
import socket
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from monitor.checks import CheckExecutionError, _run_http, _run_tls
from monitor.config import CheckConfig, Thresholds


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

