from __future__ import annotations

import unittest

from tendertrace.adapters.ebrd import EbrdAdapter, enrich_from_detail, parse_notices


LIST_HTML = """
<table><tbody><tr>
  <td><a href="viewNotice.html?displayNoticeId=45992595">
    Jordan: Package 5 Construction of Collection Systems
  </a></td>
  <td>Contract Award Notice</td>
  <td>Package 5 Construction of Collection Systems</td>
  <td>13/08/2026 11:33<br><span>UK Time</span></td>
  <td>N/A</td>
  <td>Information Only</td>
  <td>13/08/2026</td><td>202608131133</td><td></td>
  <td>[WEST IRBID WASTEWATER NETWORK PROJECT, 48496, Jordan, Works,
    Open Tender Single Stage, Water Authority Jordan (WAJ),
    Municipal and Environmental Infrastructure, Contract Award Notice]</td>
</tr></tbody></table>
"""

DETAIL_HTML = """
<div class="pure-u-24-24 mobilepadding">
  <div>
    <h1 class="entry-title">Jordan: Package 5 Construction of Collection Systems</h1>
    <div id="noticepreviewtable">
      <table id="oppoverviewtable">
        <tr><td>Project Name:</td><td>WEST IRBID WASTEWATER NETWORK PROJECT</td></tr>
        <tr><td>EBRD Project ID:</td><td>48496</td></tr>
        <tr><td>Country:</td><td>Jordan</td></tr>
        <tr><td>Client Name:</td><td>Water Authority Jordan (WAJ)</td></tr>
        <tr><td>Procurement Method:</td><td>Open Tender Single Stage</td></tr>
      </table>
    </div>
    <div>Contract Description: Construction of wastewater collection networks.</div>
    <a href>Empty action</a>
    <a href="/delta/files/specification.pdf">Technical specification</a>
  </div>
</div>
"""


class EbrdAdapterTests(unittest.TestCase):
    def test_parse_and_enrich_preserve_project_evidence(self) -> None:
        notices = parse_notices(LIST_HTML)

        self.assertEqual(len(notices), 1)
        notice = enrich_from_detail(notices[0], DETAIL_HTML)
        self.assertEqual(notice.id, "45992595")
        self.assertEqual(notice.source_site, "ebrd")
        self.assertEqual(notice.publish_time, "2026-08-13")
        self.assertEqual(notice.region, "Jordan")
        self.assertEqual(notice.purchaser, "Water Authority Jordan (WAJ)")
        self.assertEqual(notice.fields["project_id"], "48496")
        self.assertEqual(notice.fields["procurement_method"], "Open Tender Single Stage")
        self.assertIn("wastewater collection", notice.content_text)
        self.assertEqual(len(notice.attachments), 1)
        self.assertTrue(notice.attachments[0].url.endswith("specification.pdf"))

    def test_adapter_routes_only_global_or_ebrd_scope(self) -> None:
        adapter = EbrdAdapter()

        self.assertTrue(adapter.supports({"region": {"scope": "global"}}))
        self.assertTrue(adapter.supports({"region": {"scope": "ebrd"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "domestic"}}))
        self.assertNotIn("cloudflare", adapter.policy.blocked_markers)
        self.assertIn("captcha", adapter.policy.blocked_markers)


if __name__ == "__main__":
    unittest.main()
