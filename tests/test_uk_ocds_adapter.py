import unittest

from tendertrace.adapters.uk_ocds import (
    CONTRACTS_FINDER_API,
    FIND_TENDER_API,
    ContractsFinderAdapter,
    FindTenderAdapter,
    build_search_url,
    parse_ocds_notices,
)


class UkOcdsAdapterTests(unittest.TestCase):
    def test_parse_release_extracts_evidence_and_commercial_fields(self) -> None:
        payload = {
            "releases": [
                {
                    "ocid": "ocds-test-1",
                    "id": "release-1",
                    "date": "2026-08-14T22:03:25+01:00",
                    "tag": ["tender"],
                    "buyer": {"name": "Example Council"},
                    "tender": {
                        "title": "Data centre server refresh",
                        "description": "Supply and support of rack servers.",
                        "status": "active",
                        "classification": {
                            "id": "48820000",
                            "description": "Servers",
                        },
                        "items": [
                            {
                                "deliveryAddresses": [
                                    {"region": "London", "countryName": "United Kingdom"}
                                ]
                            }
                        ],
                        "tenderPeriod": {"endDate": "2026-09-01T12:00:00Z"},
                        "value": {"amount": 250000, "currency": "GBP"},
                        "documents": [
                            {
                                "title": "Specification",
                                "url": "https://example.gov/specification.pdf",
                                "format": "application/pdf",
                            },
                            {
                                "description": "Tender notice",
                                "url": "https://example.gov/notice/1",
                                "format": "text/html",
                            },
                        ],
                    },
                }
            ]
        }

        notices = parse_ocds_notices(
            payload,
            source_site="contracts_finder",
            authority="UK Contracts Finder",
        )

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.id, "release-1")
        self.assertEqual(notice.source_site, "contracts_finder")
        self.assertEqual(notice.region, "London, United Kingdom")
        self.assertEqual(notice.source_url, "https://example.gov/notice/1")
        self.assertEqual(notice.attachments[0].url, "https://example.gov/specification.pdf")
        self.assertEqual(notice.fields["cluster_key"], "ocds:ocds-test-1")
        self.assertEqual(notice.fields["estimated_value"], "250000")
        self.assertEqual(notice.fields["currency"], "GBP")
        self.assertEqual(notice.fields["deadline"], "2026-09-01")

    def test_search_url_uses_source_specific_date_parameters(self) -> None:
        bidql = {"time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-15"}}}

        contracts_url = build_search_url(CONTRACTS_FINDER_API, bidql, limit=25)
        tender_url = build_search_url(FIND_TENDER_API, bidql, limit=25)

        self.assertIn("publishedFrom=2026-08-01", contracts_url)
        self.assertIn("publishedTo=2026-08-15", contracts_url)
        self.assertIn("updatedFrom=2026-08-01T00%3A00%3A00Z", tender_url)
        self.assertIn("updatedTo=2026-08-15T23%3A59%3A59Z", tender_url)
        self.assertIn("limit=25", tender_url)

    def test_adapters_only_run_for_global_or_uk_scope(self) -> None:
        contracts = ContractsFinderAdapter()
        find_tender = FindTenderAdapter()

        for adapter in (contracts, find_tender):
            self.assertTrue(adapter.supports({"region": {"scope": "global"}}))
            self.assertTrue(adapter.supports({"region": {"scope": "uk"}}))
            self.assertFalse(adapter.supports({"region": {"scope": "domestic"}}))


if __name__ == "__main__":
    unittest.main()
