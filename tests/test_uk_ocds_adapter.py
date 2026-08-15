import unittest

from tendertrace.adapters.uk_ocds import (
    CONTRACTS_FINDER_API,
    FIND_TENDER_API,
    ContractsFinderAdapter,
    FindTenderAdapter,
    build_search_form,
    build_search_url,
    parse_ocds_notices,
    parse_search_candidates,
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

    def test_public_search_candidates_map_traceable_result_fields(self) -> None:
        html = """
        <div class="search-result">
          <div class="search-result-header">
            <a href="https://www.contractsfinder.service.gov.uk/notice/3abc9982-6f43-4d46-aa0e-2ac399599e7a?origin=SearchResults&p=1">Server platform</a>
          </div>
          <div class="search-result-sub-header">Example Council</div>
          <div class="search-result-entry"><strong>Procurement stage</strong> Opportunity</div>
          <div class="search-result-entry"><strong>Notice status</strong> Open</div>
          <div class="search-result-entry"><strong>Closing</strong> 7 September 2026, 12pm</div>
          <div class="search-result-entry"><strong>Contract location</strong> London</div>
          <div class="search-result-entry"><strong>Contract value</strong> £250,000</div>
          <div class="search-result-entry"><strong>Publication date</strong> 14 August 2026, 4:18pm</div>
        </div>
        """

        candidates = parse_search_candidates(html, source_site="contracts_finder")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].notice_id, "3abc9982-6f43-4d46-aa0e-2ac399599e7a")
        self.assertEqual(candidates[0].publish_time, "2026-08-14")
        self.assertEqual(candidates[0].purchaser, "Example Council")
        self.assertEqual(candidates[0].region, "London")
        self.assertEqual(candidates[0].fields["estimated_value"], "£250,000")
        self.assertNotIn("?", candidates[0].source_url)

    def test_search_form_reuses_checked_defaults_token_and_window(self) -> None:
        html = """
        <form id="search_form">
          <input type="hidden" name="form_token" value="safe-token">
          <input type="checkbox" name="stage[1]" value="1" checked="checked">
          <input type="checkbox" name="stage[2]" value="1">
          <input type="checkbox" name="open" value="1">
          <input name="published_from[day]"><input name="published_from[month]"><input name="published_from[year]">
          <input name="published_to[day]"><input name="published_to[month]"><input name="published_to[year]">
        </form>
        """

        payload = build_search_form(
            html,
            term="server",
            bidql={"time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-16"}}},
        )

        self.assertEqual(payload["form_token"], "safe-token")
        self.assertEqual(payload["stage[1]"], "1")
        self.assertNotIn("stage[2]", payload)
        self.assertEqual(payload["open"], "1")
        self.assertEqual(payload["keywords"], "server")
        self.assertEqual(payload["published_from[day]"], "1")
        self.assertEqual(payload["published_to[day]"], "16")


if __name__ == "__main__":
    unittest.main()
