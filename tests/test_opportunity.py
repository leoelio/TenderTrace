from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.opportunity import (
    analyze_opportunity_payload,
    enrich_opportunity_intelligence,
    list_opportunities,
)


class OpportunityIntelligenceTests(unittest.TestCase):
    def test_complete_recent_notice_becomes_actionable_opportunity(self) -> None:
        notice = _notice()

        result = enrich_opportunity_intelligence(
            [notice],
            as_of=datetime(2026, 8, 15, 10, 0),
        )

        intelligence = result.notices[0].fields["opportunity_intelligence"]
        self.assertIn(intelligence["level"], {"A", "B"})
        self.assertGreaterEqual(intelligence["score"], 65)
        self.assertGreaterEqual(intelligence["scores"]["credibility"], 80)
        self.assertEqual(intelligence["stage"], "机会确认")
        self.assertTrue(intelligence["recommended_actions"])
        self.assertEqual(result.stats["opportunity_analyzed"], 1)

    def test_missing_evidence_is_exposed_instead_of_hidden(self) -> None:
        intelligence = analyze_opportunity_payload(
            {"标题": "服务器采购公告", "发布时间": "2026-08-14"},
            as_of=datetime(2026, 8, 15, 10, 0),
        )

        self.assertLess(intelligence["scores"]["completeness"], 50)
        self.assertIn("来源链接", intelligence["missing_fields"])
        self.assertTrue(any("证据" in item for item in intelligence["risks"]))

    def test_local_opportunity_list_uses_persisted_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            notice = enrich_opportunity_intelligence(
                [_notice()],
                as_of=datetime(2026, 8, 15, 10, 0),
            ).notices[0]
            with connection(settings) as conn:
                conn.execute(
                    """
                    INSERT INTO notices(
                        id, source_site, source_url, canonical_url, title, publish_time,
                        region, purchaser, content_text, core_content, attachments_json, fields_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ccgp:n1",
                        notice.source_site,
                        notice.source_url,
                        notice.source_url,
                        notice.title,
                        notice.publish_time,
                        notice.region,
                        notice.purchaser,
                        notice.content_text,
                        notice.core_content,
                        json_dumps([{"name": item.name, "url": item.url} for item in notice.attachments]),
                        json_dumps(notice.fields),
                    ),
                )

            payload = list_opportunities(settings, limit=10)

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["items"][0]["notice_id"], "ccgp:n1")
        self.assertTrue(payload["items"][0]["intelligence"]["project_target"])


def _notice() -> Notice:
    return Notice(
        id="n1",
        source_site="ccgp",
        title="上海某单位服务器采购公开招标公告",
        publish_time="2026-08-13",
        region="上海",
        purchaser="上海某单位",
        source_url="https://www.ccgp.gov.cn/detail/n1.htm",
        content_text="项目编号 SH-2026-001，预算120万元，投标截止2026-08-28。",
        core_content="服务器采购，预算120万元。",
        attachments=[Attachment(name="采购需求", url="https://example.com/spec.pdf")],
        fields={
            "duplicate_count": 2,
            "structured_fields": {
                "project_no": "SH-2026-001",
                "purchaser": "上海某单位",
                "budget": "120万元",
                "bid_deadline": "2026-08-28",
            },
            "evidence": {
                "status": "passed",
                "quality_score": 0.95,
                "excerpt": "项目编号 SH-2026-001，预算120万元。",
                "snapshot_sha256": "a" * 64,
            },
        },
    )


if __name__ == "__main__":
    unittest.main()
