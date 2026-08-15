import socket
import unittest

import httpx

from tendertrace.public_http import UnsafeUrlError, ensure_public_http_url, fetch_public_bytes


def public_resolver(host: str, port: int, **_: object):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


class PublicHttpTests(unittest.TestCase):
    def test_rejects_local_private_and_credential_urls(self) -> None:
        for url in (
            "http://127.0.0.1/admin",
            "http://169.254.169.254/latest/meta-data",
            "http://user:password@example.com/private",
            "file:///etc/passwd",
            "http://localhost:8000/api/health",
        ):
            with self.subTest(url=url), self.assertRaises(UnsafeUrlError):
                ensure_public_http_url(url, resolve=False)

    def test_rejects_hostname_resolving_to_private_address(self) -> None:
        def private_resolver(host: str, port: int, **_: object):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", port))]

        with self.assertRaises(UnsafeUrlError):
            ensure_public_http_url(
                "https://internal.example.com/tender",
                resolver=private_resolver,
            )

    def test_fetch_follows_only_public_redirects_and_limits_bytes(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/start":
                return httpx.Response(302, headers={"Location": "/notice"})
            return httpx.Response(200, content=b"public tender body")

        transport = httpx.MockTransport(handler)

        def factory(**kwargs):
            return httpx.Client(transport=transport, **kwargs)
        result = fetch_public_bytes(
            "https://example.com/start",
            max_bytes=100,
            resolver=public_resolver,
            http_client_factory=factory,
        )

        self.assertEqual(result.final_url, "https://example.com/notice")
        self.assertEqual(result.data, b"public tender body")

        with self.assertRaises(ValueError):
            fetch_public_bytes(
                "https://example.com/notice",
                max_bytes=5,
                resolver=public_resolver,
                http_client_factory=factory,
            )

    def test_fetch_blocks_redirect_to_private_network(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1/admin"},
            )
        )

        with self.assertRaises(UnsafeUrlError):
            fetch_public_bytes(
                "https://example.com/start",
                max_bytes=100,
                resolver=public_resolver,
                http_client_factory=lambda **kwargs: httpx.Client(
                    transport=transport, **kwargs
                ),
            )


if __name__ == "__main__":
    unittest.main()
