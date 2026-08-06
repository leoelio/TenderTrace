import json
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.fetching import FetchResult
from tendertrace.vault.qianlima import (
    QianlimaSessionVault,
    parse_rendered_detail,
    parse_rendered_search,
)


class QianlimaVaultTests(unittest.TestCase):
    def test_status_reports_missing_and_existing_storage_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            vault = QianlimaSessionVault(settings)

            missing = vault.status()
            settings.ensure_directories()
            vault.storage_state_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
            existing = vault.status()
            ready_state = {
                "cookies": [
                    {
                        "name": "member_session",
                        "value": "cookie-value-must-not-leak",
                        "domain": ".qianlima.com",
                        "path": "/",
                    }
                ],
                "origins": [],
            }
            vault.storage_state_path.write_text(json.dumps(ready_state), encoding="utf-8")
            ready = vault.status()

        self.assertFalse(missing.exists)
        self.assertTrue(existing.exists)
        self.assertFalse(existing.ready)
        self.assertEqual(existing.validation, "empty_state")
        self.assertTrue(ready.ready)
        self.assertEqual(ready.validation, "ready")
        self.assertEqual(ready.qianlima_cookie_count, 1)
        self.assertNotIn("cookie-value-must-not-leak", str(ready.to_dict()))
        self.assertIn("qianlima_storage_state.json", existing.storage_state_path)
        self.assertGreater(existing.size, 0)

    def test_status_rejects_invalid_storage_state_without_leaking_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            settings.ensure_directories()
            vault = QianlimaSessionVault(settings)
            vault.storage_state_path.write_text(
                '{"cookies":[{"domain":"example.com","value":"hidden"}],"origins":[]}',
                encoding="utf-8",
            )

            status = vault.status()

        self.assertFalse(status.ready)
        self.assertEqual(status.validation, "domain_missing")
        self.assertNotIn("hidden", str(status.to_dict()))

    def test_parse_rendered_search_uses_stable_cluster_key(self) -> None:
        html = """
        <html><body>
          <a href="/notice/abc.html">上海医疗设备采购公开招标公告</a>
          <a href="/notice/abc.html">上海医疗设备采购公开招标公告</a>
          <a href="/notice/other.html">北京车辆采购公告</a>
        </body></html>
        """

        notices = parse_rendered_search(html, keyword="设备")

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].source_site, "qianlima")
        self.assertEqual(notices[0].fields["collector"], "playwright")
        self.assertTrue(notices[0].fields["cluster_key"].startswith("qianlima:"))

    def test_parse_rendered_detail_enriches_login_source_notice(self) -> None:
        notice = parse_rendered_search(
            '<html><body><a href="/notice/server.html">上海服务器采购公开招标公告</a></body></html>',
            keyword="服务器",
        )[0]
        fetch_result = FetchResult(
            url=notice.source_url,
            final_url="https://search.qianlima.com/notice/server.html",
            method="GET",
            status_code=200,
            text="<html></html>",
            content_type="text/html",
            fetched_at="2026-07-06T02:00:00+00:00",
            elapsed_ms=12,
            attempt_count=1,
            fetcher="playwright",
        )

        enriched = parse_rendered_detail(
            notice,
            """
            <html>
              <body>
                <h1>上海服务器采购公开招标公告</h1>
                <main>
                  发布时间：2026年07月06日 09:30。
                  地区：上海。采购人：上海某单位。
                  项目编号：SH-QLM-2026-001。预算金额：120万元。
                </main>
                <a href="./files/spec.pdf">附件：采购需求</a>
              </body>
            </html>
            """,
            fetch_result,
        )

        self.assertEqual(enriched.publish_time, "2026-07-06 09:30")
        self.assertEqual(enriched.region, "上海")
        self.assertEqual(enriched.purchaser, "上海某单位")
        self.assertIn("SH-QLM-2026-001", enriched.content_text)
        self.assertEqual(
            enriched.attachments[0].url, "https://search.qianlima.com/notice/files/spec.pdf"
        )
        self.assertEqual(enriched.fields["page_artifact"]["fetcher"], "playwright")


if __name__ == "__main__":
    unittest.main()
