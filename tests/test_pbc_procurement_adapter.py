from __future__ import annotations

import unittest

from tendertrace.adapters.pbc_procurement import (
    PbcProcurementAdapter,
    _date_chunks,
    enrich_from_detail,
    parse_notice_payload,
)


PAYLOAD = {
    "code": "200",
    "total": 1,
    "data": [
        {
            "id": "notice-001",
            "title": "上海黄金交易所服务器采购项目招标公告",
            "pageurl": "/freecms/site/rmyh/ggxx/info/2026/notice-001.html",
            "fieldValues": {
                "f_noticeTime": "2026-08-14 16:45:51",
                "f_noticeName": "上海黄金交易所服务器采购项目招标公告",
                "f_noticeType": "001011",
                "f_noticeTypeName": "公开招标采购公告",
                "f_openTenderCode": "PBC-2026-001",
                "f_planCodes": "PLAN-001",
                "f_purchaser": "上海黄金交易所",
                "f_purchaserAddr": "上海市浦东新区示例路1号",
                "f_catalogueNameList": "A02010104 服务器",
                "f_budget": "1900000.0000",
                "f_openTenderTime": "2026-09-10 14:00:00",
                "f_expireTime": "2026-09-10 14:00:00",
                "f_agency": "中国人民银行集中采购中心",
                "f_regionName": "人民银行",
                "attachList": '[{"fileName":"技术需求.pdf","fileUrl":"/files/spec.pdf"}]',
            },
        }
    ],
}

DETAIL_HTML = """
<html><body>
  <div id="noticeArea">
    <h4>一、项目基本情况</h4>
    <p>项目编号：PBC-2026-001</p>
    <p>项目名称：上海黄金交易所服务器采购项目</p>
    <p>预算金额：1,900,000.00元</p>
    <p>提交投标文件截止时间：2026年09月10日14时00分</p>
    <a href="/files/pricing.xlsx">附件：报价表</a>
  </div>
</body></html>
"""


class PbcProcurementAdapterTests(unittest.TestCase):
    def test_parse_payload_preserves_official_structured_fields(self) -> None:
        notices = parse_notice_payload(PAYLOAD)

        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.source_site, "pbc_procurement")
        self.assertEqual(notice.publish_time, "2026-08-14")
        self.assertEqual(notice.region, "上海")
        self.assertEqual(notice.purchaser, "上海黄金交易所")
        self.assertEqual(notice.fields["project_code"], "PBC-2026-001")
        self.assertEqual(notice.fields["budget"], "1900000.0000")
        self.assertEqual(notice.fields["deadline"], "2026-09-10 14:00:00")
        self.assertEqual(notice.fields["authority"], "中国人民银行集中采购中心")
        self.assertEqual(len(notice.attachments), 1)
        self.assertTrue(notice.source_url.startswith("https://jzcg.pbc.gov.cn/"))

    def test_detail_enrichment_extracts_body_and_additional_attachment(self) -> None:
        notice = parse_notice_payload(PAYLOAD)[0]

        enriched = enrich_from_detail(notice, DETAIL_HTML)

        self.assertIn("预算金额", enriched.content_text)
        self.assertIn("PBC-2026-001", enriched.core_content)
        self.assertEqual(enriched.fields["content_selector"], "#noticeArea")
        self.assertEqual(len(enriched.attachments), 2)

    def test_long_windows_are_split_to_official_one_year_limit(self) -> None:
        chunks = _date_chunks(
            {
                "time": {
                    "resolved_window": {"from": "2024-01-01", "to": "2026-08-16"}
                }
            }
        )

        self.assertEqual(chunks[0][0].isoformat(), "2024-01-01")
        self.assertEqual(chunks[-1][1].isoformat(), "2026-08-16")
        self.assertTrue(all((end - start).days <= 364 for start, end in chunks))

    def test_adapter_routes_only_domestic_scope(self) -> None:
        adapter = PbcProcurementAdapter()

        self.assertTrue(adapter.supports({"region": {"scope": "domestic"}}))
        self.assertFalse(adapter.supports({"region": {"scope": "global"}}))

    def test_parser_rejects_unexpected_response(self) -> None:
        with self.assertRaisesRegex(ValueError, "schema"):
            parse_notice_payload({"code": "500", "data": []})


if __name__ == "__main__":
    unittest.main()
