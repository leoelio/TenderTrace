from __future__ import annotations

from urllib.parse import parse_qs, urlparse
import unittest

from tendertrace.adapters.idb import build_search_url, parse_notices


class IdbAdapterTests(unittest.TestCase):
    def test_build_search_url_uses_terms_window_sort_and_pagination(self) -> None:
        url = build_search_url(
            {
                "topic": {"source_terms": ["server", "supplier's platform"]},
                "time": {"resolved_window": {"from": "2026-08-01", "to": "2026-08-16"}},
            },
            page=2,
            limit=20,
        )

        self.assertIsNotNone(url)
        assert url is not None
        sql = parse_qs(urlparse(url).query)["sql"][0]
        self.assertIn('lower("noticetitle") LIKE \'%server%\'', sql)
        self.assertIn("supplier''s platform", sql)
        self.assertIn('"publicationdate" >= \'2026-08-01\'', sql)
        self.assertIn('ORDER BY "publicationdate" DESC', sql)
        self.assertIn("LIMIT 20 OFFSET 20", sql)

    def test_parse_notices_maps_traceable_official_fields(self) -> None:
        notices = parse_notices(
            {
                "success": True,
                "result": {
                    "records": [
                        {
                            "noticeid": "38662",
                            "type": "SPECIFIC",
                            "countryname": "EL SALVADOR",
                            "projectnumber": "ES-L1138",
                            "proyecturl": "https://www.iadb.org/en/project/ES-L1138",
                            "loannumber": "1234/OC-ES",
                            "noticetitle": "Adquisicion de Mamografia digital",
                            "documenturl": "https://idbdocs.iadb.org/wsdocs/getdocument.aspx?docnum=1",
                            "projectname": "Health services program",
                            "publicationdate": "2026-08-12 04:00:00.000000000",
                            "deadline": "2026-09-01",
                            "sectorenglnm": "HEALTH",
                            "prcrmnt_mthd_engl_nm": "International competitive bidding",
                        },
                        {
                            "noticeid": "missing-link",
                            "noticetitle": "Record without traceable source",
                            "publicationdate": "2026-08-12 04:00:00.000000000",
                        },
                    ]
                },
            }
        )

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.source_site, "idb")
        self.assertEqual(notice.publish_time, "2026-08-12")
        self.assertEqual(notice.region, "EL SALVADOR")
        self.assertEqual(notice.fields["project_id"], "ES-L1138")
        self.assertEqual(notice.fields["deadline"], "2026-09-01")
        self.assertEqual(notice.fields["authority"], "Inter-American Development Bank")
        self.assertEqual(notice.source_url, "https://idbdocs.iadb.org/wsdocs/getdocument.aspx?docnum=1")
        self.assertEqual(notice.attachments, [])


if __name__ == "__main__":
    unittest.main()
