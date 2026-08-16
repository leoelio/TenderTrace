from __future__ import annotations

from urllib.parse import parse_qs, urlparse
import unittest

import httpx

from tendertrace.adapters.prozorro import (
    ProzorroAdapter,
    _source_terms,
    build_feed_url,
    parse_tender,
)


INTERNAL_ID = "a" * 32


def _detail_payload() -> dict[str, object]:
    return {
        "data": {
            "id": INTERNAL_ID,
            "tenderID": "UA-2026-08-14-000001-a",
            "date": "2026-08-14T09:30:00+03:00",
            "dateModified": "2026-08-14T10:00:00+03:00",
            "title": "Постачання серверного обладнання",
            "description": "Сервери для центру обробки даних",
            "status": "active.tendering",
            "procurementMethodType": "aboveThresholdUA",
            "procuringEntity": {
                "name": "Державна установа",
                "address": {"locality": "Київ", "countryName": "Україна"},
            },
            "tenderPeriod": {"endDate": "2026-09-01T12:00:00+03:00"},
            "value": {"amount": 2500000, "currency": "UAH"},
            "items": [
                {
                    "description": "Серверне обладнання",
                    "classification": {"id": "48820000-2", "description": "Сервери"},
                    "deliveryAddress": {"locality": "Київ", "countryName": "Україна"},
                }
            ],
            "documents": [
                {"title": "Технічна специфікація", "url": "https://public-docs.prozorro.gov.ua/spec.pdf"}
            ],
        }
    }


class ProzorroAdapterTests(unittest.TestCase):
    def test_fire_topic_expands_as_a_phrase(self) -> None:
        terms = _source_terms({"topic": {"source_terms": ["fire"]}})

        self.assertIn("пожежн", terms)
        self.assertNotIn("п", terms)

    def test_feed_url_starts_from_requested_window_end(self) -> None:
        url = build_feed_url(
            {"time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-16"}}},
            limit=1200,
        )
        query = parse_qs(urlparse(url).query)

        self.assertEqual(query["descending"], ["1"])
        self.assertEqual(query["limit"], ["1000"])
        self.assertEqual(query["offset"], ["2026-08-16T23:59:59+03:00"])

    def test_parse_tender_preserves_commercial_and_evidence_fields(self) -> None:
        notice = parse_tender(_detail_payload())

        self.assertIsNotNone(notice)
        assert notice is not None
        self.assertEqual(notice.source_site, "prozorro")
        self.assertEqual(notice.publish_time, "2026-08-14")
        self.assertIn("Київ", notice.region)
        self.assertEqual(notice.fields["deadline"], "2026-09-01")
        self.assertEqual(notice.fields["estimated_value"], "2500000")
        self.assertEqual(notice.fields["currency"], "UAH")
        self.assertEqual(len(notice.attachments), 1)

    def test_collect_uses_feed_detail_and_ukrainian_topic_expansion(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(f"/tenders/{INTERNAL_ID}"):
                return httpx.Response(200, json=_detail_payload())
            return httpx.Response(
                200,
                json={
                    "data": [{"id": INTERNAL_ID, "dateModified": "2026-08-14T10:00:00+03:00"}],
                    "next_page": {},
                },
            )

        adapter = ProzorroAdapter(transport=httpx.MockTransport(handler))
        notices = adapter.collect(
            {
                "region": {"scope": "ukraine"},
                "topic": {"source_terms": ["server"]},
                "time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-16"}},
            },
            max_results=5,
        )

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].fields["tender_id"], "UA-2026-08-14-000001-a")
        self.assertEqual(adapter.last_fetch_stats["requests"], 2)

    def test_adapter_routes_only_ukraine_and_global_scope(self) -> None:
        adapter = ProzorroAdapter()

        self.assertTrue(adapter.supports({"region": {"scope": "ukraine"}}))
        self.assertTrue(adapter.supports({"region": {"scope": "global"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "domestic"}}))


if __name__ == "__main__":
    unittest.main()
