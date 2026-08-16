from __future__ import annotations

import unittest

from tendertrace.adapters.adb import AdbAdapter, _matches_terms, parse_notices


ADB_HTML = """
<h2>Invitation to Bid</h2>
<table>
  <thead><tr><th>Title</th><th>Start date</th><th>End date</th></tr></thead>
  <tbody>
    <tr>
      <td>
        <a href="/sites/default/files/page/559266/itb-ai-security.pdf">
          Invitation to Bid: AI Security Platform
        </a>
        <em>Deadline for clarifications: 20 August 2026</em>
      </td>
      <td>14 August 2026</td>
      <td>31 August 2026, 5:00 p.m. (Manila time)</td>
    </tr>
  </tbody>
</table>
"""


class AdbAdapterTests(unittest.TestCase):
    def test_parse_notices_preserves_official_pdf_and_deadline(self) -> None:
        notices = parse_notices(ADB_HTML)

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.id, "itb-ai-security")
        self.assertEqual(notice.source_site, "adb")
        self.assertEqual(notice.publish_time, "2026-08-14")
        self.assertEqual(notice.purchaser, "Asian Development Bank")
        self.assertEqual(notice.fields["deadline"], "2026-08-31")
        self.assertEqual(notice.fields["notice_type"], "Invitation to Bid")
        self.assertEqual(notice.attachments[0].url, notice.source_url)
        self.assertTrue(notice.source_url.endswith("/itb-ai-security.pdf"))
        self.assertTrue(_matches_terms(notice, ["security"]))
        self.assertFalse(_matches_terms(notice, ["elevator"]))

    def test_adapter_routes_only_global_or_adb_scope(self) -> None:
        adapter = AdbAdapter()

        self.assertNotIn("cloudflare", adapter.policy.blocked_markers)
        self.assertTrue(adapter.supports({"region": {"scope": "global"}}))
        self.assertTrue(adapter.supports({"region": {"scope": "adb"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "domestic"}}))


if __name__ == "__main__":
    unittest.main()
