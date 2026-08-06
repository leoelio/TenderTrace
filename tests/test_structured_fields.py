import unittest

from tendertrace.adapters.ccgp import Notice
from tendertrace.pipeline.fields import extract_structured_fields


class StructuredFieldsTests(unittest.TestCase):
    def test_extracts_procurement_fields_from_notice_text(self) -> None:
        notice = Notice(
            id="field-1",
            source_site="ccgp",
            title="服务器采购公开招标公告",
            publish_time="2026-07-06 09:30",
            region="上海",
            purchaser="上海某单位",
            source_url="https://example.com/detail.html",
            content_text=(
                "项目编号：SH-2026-001。预算金额：120万元。"
                "投标截止时间：2026年7月20日 09:30。开标时间：2026-07-20 10:00。"
            ),
            core_content="服务器采购。",
        )

        result = extract_structured_fields([notice])
        structured = result.notices[0].fields["structured_fields"]
        evidence = result.notices[0].fields["structured_field_evidence"]

        self.assertEqual(structured["project_no"], "SH-2026-001")
        self.assertEqual(structured["budget"], "120万元")
        self.assertIn("2026年7月20日", structured["bid_deadline"])
        self.assertEqual(structured["opening_time"], "2026-07-20 10:00")
        self.assertEqual(evidence["budget"]["value"], "120万元")
        self.assertIn("预算金额", evidence["budget"]["evidence_text"])
        self.assertEqual(evidence["budget"]["source_url"], "https://example.com/detail.html")
        self.assertEqual(result.stats["structured_field_hits"], 7)

    def test_extracts_english_project_number_for_overseas_sources(self) -> None:
        notice = Notice(
            id="field-2",
            source_site="overseas",
            title="Server procurement tender",
            publish_time="2026-07-06",
            region="Singapore",
            purchaser="Buyer",
            source_url="https://example.com/overseas.html",
            content_text="Project No: SG-2026-778. Budget: 2 million CNY. Bid deadline: 2026-08-01.",
            core_content="Server procurement.",
        )

        structured = extract_structured_fields([notice]).notices[0].fields["structured_fields"]

        self.assertEqual(structured["project_no"], "SG-2026-778")
        self.assertEqual(structured["budget"], "2 million CNY")
        self.assertEqual(structured["bid_deadline"], "2026-08-01")


if __name__ == "__main__":
    unittest.main()
