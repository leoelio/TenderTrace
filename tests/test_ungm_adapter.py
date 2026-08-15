from __future__ import annotations

import unittest

from tendertrace.adapters.ungm import (
    UngmAdapter,
    build_search_body,
    enrich_from_detail,
    parse_search_results,
)


SEARCH_HTML = """
<div role="row" data-noticeid="310935" class="tableRow dataRow notice-table">
  <div class="tableCell resultOptions"></div>
  <div class="tableCell resultTitle"><span class="ungm-title">Server platform</span></div>
  <div class="tableCell resultInfo1 deadline"><span>26-Aug-2026 23:59 (GMT 3.00)</span></div>
  <div class="tableCell"><span>13-Aug-2026</span></div>
  <div class="tableCell resultAgency"><span>WHO</span></div>
  <div class="tableCell"><span>Invitation to bid</span></div>
  <div class="tableCell resultInfo1"><span>WHO-ITB-9362</span></div>
  <div class="tableCell"><span>Pakistan</span></div>
</div>
"""


DETAIL_HTML = """
<div class="ungm-panel">
  <div class="ungm-list-item ungm-background">
    <div class="title">Description</div>
    <div>Supply, installation, and configuration of data system servers.</div>
    <a href="/Shared/Documents/specification.pdf">Technical specification</a>
  </div>
</div>
"""


class UngmAdapterTests(unittest.TestCase):
    def test_build_search_body_uses_term_window_and_page(self) -> None:
        body = build_search_body(
            {
                "time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-16"}}
            },
            page=2,
            term="server",
            page_size=30,
        )

        self.assertEqual(body["PageIndex"], 2)
        self.assertEqual(body["PageSize"], 30)
        self.assertEqual(body["Title"], "server")
        self.assertEqual(body["PublishedFrom"], "01-Aug-26")
        self.assertEqual(body["PublishedTo"], "16-Aug-26")

    def test_parse_and_enrich_preserve_official_evidence(self) -> None:
        notices = parse_search_results(SEARCH_HTML)

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.id, "ungm-310935")
        self.assertEqual(notice.publish_time, "2026-08-13")
        self.assertEqual(notice.purchaser, "WHO")
        self.assertEqual(notice.region, "Pakistan")
        self.assertEqual(notice.fields["reference"], "WHO-ITB-9362")
        self.assertEqual(notice.fields["source_tier"], "official")

        enriched = enrich_from_detail(notice, DETAIL_HTML)

        self.assertIn("installation", enriched.content_text)
        self.assertEqual(len(enriched.attachments), 1)
        self.assertEqual(
            enriched.attachments[0].url,
            "https://www.ungm.org/Shared/Documents/specification.pdf",
        )

    def test_adapter_only_runs_for_global_scope(self) -> None:
        adapter = UngmAdapter()

        self.assertTrue(adapter.supports({"region": {"scope": "global"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "domestic"}}))


if __name__ == "__main__":
    unittest.main()
