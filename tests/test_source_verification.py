import socket
import unittest

import httpx

from tendertrace.public_http import UnsafeUrlError
from tendertrace.source_verification import verify_source_url


def public_resolver(host: str, port: int, **_: object):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


class SourceVerificationTests(unittest.TestCase):
    def test_verifies_public_html_and_extracts_main_text(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=(
                    "<html><nav>navigation</nav><main><h1>服务器采购公告</h1>"
                    "<p>采购机架式服务器、存储设备及三年维保服务。</p></main></html>"
                ),
            )
        )

        result = verify_source_url(
            "https://example.com/tender/1",
            resolver=public_resolver,
            http_client_factory=lambda **kwargs: httpx.Client(
                transport=transport, **kwargs
            ),
        )

        self.assertEqual(result.status, "verified")
        self.assertIn("服务器采购公告", result.text_excerpt)
        self.assertNotIn("navigation", result.text_excerpt)
        self.assertTrue(result.snapshot_sha256)
        self.assertEqual(result.status_code, 200)

    def test_http_failure_is_recorded_without_fabricating_evidence(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(404, text="missing"))

        result = verify_source_url(
            "https://example.com/missing",
            resolver=public_resolver,
            http_client_factory=lambda **kwargs: httpx.Client(
                transport=transport, **kwargs
            ),
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.text_excerpt, "")
        self.assertIn("404", result.error)

    def test_unsafe_url_is_rejected_instead_of_marked_as_network_failure(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            verify_source_url("http://127.0.0.1/admin")


if __name__ == "__main__":
    unittest.main()
