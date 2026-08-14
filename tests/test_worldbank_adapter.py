from __future__ import annotations

import unittest

from tendertrace.adapters.worldbank import _matches_terms, build_search_url, parse_notices


class WorldBankAdapterTests(unittest.TestCase):
    def test_build_search_url_uses_query_and_pagination(self) -> None:
        url = build_search_url("server", offset=20, rows=10)

        self.assertIn("qterm=server", url)
        self.assertIn("os=20", url)
        self.assertIn("rows=10", url)

    def test_parse_notices_preserves_project_and_deadline(self) -> None:
        notices = parse_notices(
            {
                "procnotices": [
                    {
                        "id": "OP00462300",
                        "notice_type": "Request for Bids",
                        "noticedate": "13-Aug-2026",
                        "submission_deadline_date": "2026-08-24T00:00:00Z",
                        "project_ctry_name": "Pakistan",
                        "project_id": "P178532",
                        "project_name": "Digital Infrastructure",
                        "bid_description": "Supply of data center servers",
                        "contact_organization": "Project Office",
                        "notice_text": "<p>Server procurement with installation.</p>",
                    }
                ]
            }
        )

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].publish_time, "2026-08-13")
        self.assertEqual(notices[0].region, "Pakistan")
        self.assertEqual(notices[0].fields["project_id"], "P178532")
        self.assertEqual(notices[0].fields["deadline"], "2026-08-24")
        self.assertTrue(_matches_terms(notices[0], ["server"]))
        self.assertFalse(_matches_terms(notices[0], ["elevator"]))


if __name__ == "__main__":
    unittest.main()
