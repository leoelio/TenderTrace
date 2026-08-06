from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from tendertrace.adapters.ggzy import (
    _topic_keywords,
    build_search_body,
    enrich_from_detail,
    parse_records,
)
from tendertrace.intent import compile_intent


RECORDS = [
    {
        "id": "ggzy-1",
        "publishTime": "2026-07-06",
        "transactionSourcesPlatformText": "上海政府采购网",
        "businessTypeText": "政府采购",
        "informationTypeText": "采购/资审公告",
        "province": "310000",
        "provinceText": "上海市",
        "title": "上海市某医院医疗设备采购项目公开招标公告",
        "url": "/information/deal/html/a/310000/0201/20260706/ggzy-1.html",
    }
]


DETAIL_HTML = """
<html>
  <body>
    <div id="mycontent">
      <p>项目概况：上海市某医院医疗设备采购项目的潜在投标人应在线获取招标文件。</p>
      <p>项目编号：SH-GGZY-2026-001。</p>
      <p>预算金额：300万元。</p>
      <script>window.noise = true;</script>
    </div>
    <a href="./files/spec.pdf">附件：采购需求</a>
  </body>
</html>
"""


class GgzyAdapterTests(unittest.TestCase):
    def test_build_search_body_uses_bidql_window_region_and_keyword(self) -> None:
        bidql = compile_intent(
            "2026年7月份上海设备招标信息都有哪些",
            now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        body = build_search_body(bidql, page=2)

        self.assertEqual(body["PAGENUMBER"], "2")
        self.assertEqual(body["DEAL_PROVINCE"], "310000")
        self.assertEqual(body["TIMEBEGIN"], "2026-07-01")
        self.assertEqual(body["TIMEEND"], "2026-07-31")
        self.assertEqual(body["FINDTXT"], "设备")

    def test_search_keywords_include_multiple_topics_and_expansions(self) -> None:
        bidql = compile_intent(
            "最近36个月杭州市的空调或者服务器投标信息都有哪些",
            now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        keywords = _topic_keywords(bidql)
        body = build_search_body(bidql, page=1, keyword="中央空调")

        self.assertIn("空调", keywords)
        self.assertIn("服务器", keywords)
        self.assertIn("中央空调", keywords)
        self.assertEqual(body["DEAL_PROVINCE"], "330000")
        self.assertEqual(body["FINDTXT"], "中央空调")

    def test_long_time_window_uses_site_supported_relative_filter(self) -> None:
        bidql = compile_intent(
            "最近36个月浙江省的全部投标信息都有哪些",
            now=datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )

        body = build_search_body(bidql, page=1)

        self.assertEqual(body["DEAL_PROVINCE"], "330000")
        self.assertEqual(body["DEAL_TIME"], "02")
        self.assertNotIn("TIMEBEGIN", body)
        self.assertNotIn("TIMEEND", body)

    def test_parse_records_creates_notice_with_cluster_key(self) -> None:
        notice = parse_records(RECORDS)[0]

        self.assertEqual(notice.source_site, "ggzy")
        self.assertEqual(notice.id, "ggzy-1")
        self.assertEqual(notice.region, "上海市")
        self.assertEqual(notice.purchaser, "上海政府采购网")
        self.assertEqual(notice.fields["cluster_key"], "ggzy:ggzy-1")
        self.assertEqual(
            notice.source_url,
            "https://www.ggzy.gov.cn/information/deal/html/a/310000/0201/20260706/ggzy-1.html",
        )

    def test_enrich_from_detail_extracts_content_and_attachment(self) -> None:
        notice = parse_records(RECORDS)[0]

        enriched = enrich_from_detail(notice, DETAIL_HTML, "https://www.ggzy.gov.cn/detail.html")

        self.assertIn("项目概况", enriched.core_content)
        self.assertIn("SH-GGZY-2026-001", enriched.content_text)
        self.assertNotIn("window.noise", enriched.content_text)
        self.assertEqual(enriched.attachments[0].name, "附件：采购需求")
        self.assertEqual(enriched.attachments[0].url, "https://www.ggzy.gov.cn/files/spec.pdf")


if __name__ == "__main__":
    unittest.main()
