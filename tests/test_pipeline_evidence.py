import unittest

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.pipeline.evidence import attach_evidence


class PipelineEvidenceTests(unittest.TestCase):
    def test_attach_evidence_adds_snapshot_excerpt_and_fact_checks(self) -> None:
        notice = Notice(
            id="n1",
            source_site="ccgp",
            title="上海某医院医疗设备采购公开招标公告",
            publish_time="2026-07-06 09:30",
            region="上海",
            purchaser="上海某医院",
            source_url="https://www.ccgp.gov.cn/detail.htm",
            content_text=(
                "项目编号：SH-2026-001。项目概况：上海某医院医疗设备采购。"
                "预算金额：120万元。附件：https://example.com/spec.pdf"
            ),
            core_content="项目概况：上海某医院医疗设备采购。预算金额：120万元。",
            attachments=[Attachment(name="采购需求", url="https://example.com/spec.pdf?utm_source=x")],
            fields={"project_no": "SH-2026-001"},
        )

        result = attach_evidence([notice])

        enriched = result.notices[0]
        evidence = enriched.fields["evidence"]
        self.assertEqual(result.stats["evidence_checked"], 1)
        self.assertEqual(result.stats["evidence_passed"], 1)
        self.assertEqual(enriched.fields["evidence_status"], "passed")
        self.assertEqual(len(evidence["snapshot_sha256"]), 64)
        self.assertIn("项目编号：SH-2026-001", evidence["excerpt"])
        self.assertEqual(enriched.fields["attachment_types"], ["pdf"])
        self.assertEqual(len(enriched.attachments), 1)

    def test_attach_evidence_warns_when_detail_text_is_missing(self) -> None:
        notice = Notice(
            id="n2",
            source_site="ggzy",
            title="北京充电桩建设项目招标公告",
            publish_time="2026-07-06",
            region="北京",
            purchaser="北京某公司",
            source_url="https://www.ggzy.gov.cn/detail.htm",
            core_content="预算金额：500万元。",
        )

        result = attach_evidence([notice])

        enriched = result.notices[0]
        self.assertEqual(result.stats["evidence_warnings"], 1)
        self.assertEqual(enriched.fields["evidence_status"], "warning")
        statuses = {item["field"]: item["status"] for item in enriched.fields["evidence"]["fact_checks"]}
        self.assertEqual(statuses["detail_text"], "warning")

    def test_attach_evidence_includes_attachment_snapshot_text(self) -> None:
        notice = Notice(
            id="n3",
            source_site="ccgp",
            title="上海服务器采购公开招标公告",
            publish_time="2026-07-06",
            region="上海",
            purchaser="上海某单位",
            source_url="https://www.ccgp.gov.cn/detail.htm",
            content_text="项目编号：SH-2026-ATT。详见附件。",
            core_content="服务器配置要求和交付周期。",
            attachments=[Attachment(name="采购需求", url="https://example.com/spec.docx")],
            fields={
                "attachment_snapshots": [
                    {
                        "name": "采购需求",
                        "url": "https://example.com/spec.docx",
                        "type": "docx",
                        "status": "extracted",
                        "path": "snapshots/attachments/spec.docx",
                        "sha256": "b" * 64,
                        "bytes": 1024,
                        "text_excerpt": "附件正文：服务器配置要求和交付周期。",
                        "text_length": 18,
                        "error": "",
                    }
                ]
            },
        )

        result = attach_evidence([notice])

        evidence = result.notices[0].fields["evidence"]
        self.assertEqual(evidence["attachments"][0]["status"], "extracted")
        self.assertIn("服务器配置要求", evidence["attachments"][0]["text_excerpt"])
        statuses = {item["field"]: item["status"] for item in evidence["fact_checks"]}
        self.assertEqual(statuses["core_content"], "passed")


if __name__ == "__main__":
    unittest.main()
