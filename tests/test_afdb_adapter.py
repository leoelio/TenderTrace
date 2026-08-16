from __future__ import annotations

import unittest

from tendertrace.adapters.afdb import AfdbAdapter, enrich_from_detail, parse_solicitations


LIST_HTML = """
<div class="view-content">
  <div class="views-bootstrap-grid-plugin-style">
    <div class="row">
      <div class="col-xs-12 col-md-4">
        <div class="views-field-title"><span class="field-content">
          <a href="/en/corporate-procurement/security-service-edge-95778">
            Supply and Maintenance of a Security Service Edge Solution
          </a>
        </span></div>
        <div class="views-field-field-procurement-reference">
          <div class="field-content">ADB/RFP/TCGS/2026/0194</div>
        </div>
        <div class="views-field-field-procurement-pub-date">
          <div class="field-content">27-Jul-2026</div>
        </div>
        <div class="views-field-field-procurement-end-date">
          <div class="field-content">24-Aug-2026</div>
        </div>
      </div>
    </div>
  </div>
</div>
"""

DETAIL_HTML = """
<article>
  <div class="field-name-body">
    The Bank invites experienced companies to provide a security service edge solution.
  </div>
  <a href="/files/security-notice.pdf">Procurement Notice</a>
  <a href="https://www.afdb.org/files/security-rfp.pdf">Request for Proposals</a>
</article>
"""


class AfdbAdapterTests(unittest.TestCase):
    def test_parse_and_enrich_preserve_reference_deadline_and_documents(self) -> None:
        notices = parse_solicitations(LIST_HTML)

        self.assertEqual(len(notices), 1)
        notice = enrich_from_detail(notices[0], DETAIL_HTML)
        self.assertEqual(notice.source_site, "afdb")
        self.assertEqual(notice.publish_time, "2026-07-27")
        self.assertEqual(notice.fields["reference"], "ADB/RFP/TCGS/2026/0194")
        self.assertEqual(notice.fields["deadline"], "2026-08-24")
        self.assertEqual(notice.fields["notice_type"], "RFP")
        self.assertEqual(notice.region, "Africa")
        self.assertIn("experienced companies", notice.content_text)
        self.assertEqual(len(notice.attachments), 2)
        self.assertTrue(all(item.url.endswith(".pdf") for item in notice.attachments))

    def test_adapter_routes_only_global_or_afdb_scope(self) -> None:
        adapter = AfdbAdapter()

        self.assertNotIn("cloudflare", adapter.policy.blocked_markers)
        self.assertTrue(adapter.supports({"region": {"scope": "global"}}))
        self.assertTrue(adapter.supports({"region": {"scope": "afdb"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "domestic"}}))


if __name__ == "__main__":
    unittest.main()
