from __future__ import annotations

import unittest

from tendertrace.adapters.ted import build_search_body, parse_notices


class TedAdapterTests(unittest.TestCase):
    def test_build_search_body_uses_bilingual_source_terms_and_window(self) -> None:
        body = build_search_body(
            {
                "topic": {"source_terms": ["server", "data center server"]},
                "time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-15"}},
            },
            page=2,
            limit=20,
        )

        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn('title-proc ~ "server"', str(body["query"]))
        self.assertIn("publication-date >= 20260801", str(body["query"]))
        self.assertEqual(body["page"], 2)

    def test_parse_notices_maps_multilingual_fields_and_links(self) -> None:
        notices = parse_notices(
            {
                "notices": [
                    {
                        "publication-number": "460-2025",
                        "publication-date": "2025-01-02+01:00",
                        "title-proc": {"deu": "Server-Switches"},
                        "description-proc": {"eng": "Supply of network servers"},
                        "buyer-name": {"eng": ["City IT Office"]},
                        "place-of-performance-country-proc": ["DEU"],
                        "deadline-date-lot": ["2025-02-01"],
                        "links": {"htmlDirect": {"ENG": "https://ted.europa.eu/en/notice/460-2025/html"}},
                    }
                ]
            }
        )

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].source_site, "ted")
        self.assertEqual(notices[0].purchaser, "City IT Office")
        self.assertEqual(notices[0].fields["deadline"], "2025-02-01")


if __name__ == "__main__":
    unittest.main()
