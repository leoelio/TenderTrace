import unittest

import httpx

from tendertrace.fetching import FetchError, FetchPolicy, ManagedFetcher
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


class ManagedFetcherTests(unittest.TestCase):
    def test_retries_retryable_status_and_records_stats(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, text="busy")
            return httpx.Response(200, text="<html><body>ok</body></html>")

        policy = FetchPolicy(max_retries=1, backoff_seconds=0)
        with ManagedFetcher(policy, transport=httpx.MockTransport(handler)) as fetcher:
            result = fetcher.get("https://example.com/page")

        self.assertTrue(result.ok)
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(fetcher.stats.to_dict()["retries"], 1)
        self.assertEqual(fetcher.stats.to_dict()["succeeded"], 1)

    def test_detects_blocked_marker(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html>captcha required</html>")
        )

        with ManagedFetcher(FetchPolicy(max_retries=0), transport=transport) as fetcher:
            result = fetcher.get("https://example.com/protected")

        self.assertTrue(result.blocked)
        self.assertFalse(result.ok)
        with self.assertRaises(FetchError):
            result.raise_for_status()
        self.assertEqual(fetcher.stats.to_dict()["blocked"], 1)

    def test_page_artifact_contains_traceable_fetch_metadata(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, text="<html><h1>Tender title</h1></html>")
        )

        with ManagedFetcher(FetchPolicy(max_retries=0), transport=transport) as fetcher:
            result = fetcher.get("https://example.com/tender")

        artifact = page_artifact_from_fetch("demo", result)

        self.assertEqual(artifact["source_site"], "demo")
        self.assertEqual(artifact["source_url"], "https://example.com/tender")
        self.assertEqual(artifact["status_code"], 200)
        self.assertEqual(artifact["fetcher"], "httpx")
        self.assertEqual(artifact["content_length"], len(result.text))
        self.assertTrue(artifact["content_sha256"])

    def test_batch_get_preserves_result_order_and_stats(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=f"body:{request.url.path}")

        urls = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
        with ManagedFetcher(
            FetchPolicy(max_retries=0),
            transport=httpx.MockTransport(handler),
        ) as fetcher:
            results = fetcher.batch_get(urls, max_workers=2)

        self.assertEqual([result.url for result in results], urls)
        self.assertEqual([result.text for result in results], ["body:/a", "body:/b", "body:/c"])
        self.assertEqual(fetcher.stats.to_dict()["requests"], 3)
        self.assertEqual(fetcher.stats.to_dict()["succeeded"], 3)


if __name__ == "__main__":
    unittest.main()
