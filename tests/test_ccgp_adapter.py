from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from tendertrace.adapters.ccgp import enrich_from_detail, parse_list_page
from tendertrace.intent import compile_intent


LIST_HTML = """
<html>
  <body>
    <ul class="c_list_bid">
      <li>
        <a href="./202607/t20260706_123.htm">上海某单位服务器采购公开招标公告</a>
        <span>发布时间： 2026-07-06 09:30 地域： 上海 采购人： 上海某单位</span>
      </li>
      <li>
        <a href="/cggg/dfgg/gkzb/202607/t20260705_456.htm">北京充电桩建设项目公开招标公告</a>
        <span>发布时间： 2026-07-05 10:00 地域： 北京 采购人： 北京某公司</span>
      </li>
    </ul>
  </body>
</html>
"""


DETAIL_HTML = """
<html>
  <body>
    <div id="noticeArea">
      <p>项目概况：上海某单位服务器采购公开招标项目的潜在投标人应在线获取招标文件。</p>
      <p>项目编号：SH-2026-001。</p>
      <p>预算金额：120万元。</p>
      <script>window.noise = true;</script>
    </div>
    <a href="../files/spec.docx">附件：采购需求</a>
  </body>
</html>
"""


class CcgpAdapterTests(unittest.TestCase):
    def test_parse_list_page_extracts_notice_metadata(self) -> None:
        notices = parse_list_page(LIST_HTML, "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/")

        self.assertEqual(len(notices), 2)
        self.assertEqual(notices[0].title, "上海某单位服务器采购公开招标公告")
        self.assertEqual(notices[0].publish_time, "2026-07-06 09:30")
        self.assertEqual(notices[0].region, "上海")
        self.assertEqual(notices[0].purchaser, "上海某单位")
        self.assertEqual(
            notices[0].source_url,
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202607/t20260706_123.htm",
        )

    def test_detail_enrichment_keeps_fact_text_and_attachments(self) -> None:
        notice = parse_list_page(LIST_HTML, "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/")[0]

        enriched = enrich_from_detail(notice, DETAIL_HTML)

        self.assertIn("项目概况", enriched.core_content)
        self.assertIn("SH-2026-001", enriched.core_content)
        self.assertNotIn("window.noise", enriched.content_text)
        self.assertEqual(enriched.attachments[0].name, "附件：采购需求")
        self.assertEqual(
            enriched.attachments[0].url,
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/files/spec.docx",
        )
        self.assertEqual(enriched.fields["content_selector"], "#noticeArea")

    def test_detail_enrichment_falls_back_when_known_selector_is_missing(self) -> None:
        notice = parse_list_page(LIST_HTML, "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/")[0]

        enriched = enrich_from_detail(
            notice,
            """
            <html>
              <body>
                <section class="new-layout">
                  Project overview: server procurement detail body with budget and deadline.
                </section>
                <div>short</div>
              </body>
            </html>
            """,
        )

        self.assertIn("server procurement detail", enriched.content_text)
        self.assertTrue(enriched.fields["content_fallback"])

    def test_compiled_bidql_can_filter_fixture_notice(self) -> None:
        bidql = compile_intent(
            "最近1个月的上海区域内的服务器招标信息都有哪些",
            now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        notice = parse_list_page(LIST_HTML, "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/")[0]
        enriched = enrich_from_detail(notice, DETAIL_HTML)

        self.assertEqual(bidql["region"]["province"], "上海")
        self.assertIn("服务器", enriched.content_text)


if __name__ == "__main__":
    unittest.main()
