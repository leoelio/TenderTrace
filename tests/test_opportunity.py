from dataclasses import replace
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.opportunity import (
    analyze_opportunity_payload,
    build_market_context,
    enrich_opportunity_intelligence,
    market_benchmark_for_notice,
    parse_budget_cny,
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
        self.assertEqual(intelligence["evaluated_at"], "2026-08-15")
        self.assertEqual(result.stats["opportunity_analyzed"], 1)

    def test_budget_normalization_supports_chinese_and_english_units(self) -> None:
        self.assertEqual(parse_budget_cny("预算金额 120 万元"), 1_200_000)
        self.assertEqual(parse_budget_cny("2 million CNY"), 2_000_000)
        self.assertEqual(parse_budget_cny("最高限价 1,280,000元"), 1_280_000)

    def test_market_context_uses_comparable_category_samples(self) -> None:
        notices = [
            _market_notice("n1", "100万元", "客户甲"),
            _market_notice("n2", "120万元", "客户甲"),
            _market_notice("n3", "300万元", "客户乙"),
        ]

        market = build_market_context(notices, as_of=datetime(2026, 8, 15, 10, 0))
        benchmark = market_benchmark_for_notice(notices[2], market)

        self.assertEqual(market["budget_sample_count"], 3)
        self.assertEqual(market["budget"]["median_cny"], 1_200_000)
        self.assertEqual(market["top_purchasers"][0], {"name": "客户甲", "count": 2})
        self.assertEqual(benchmark["status"], "ready")
        self.assertEqual(benchmark["position"], "above")
        self.assertIn("可比样本 3 条", benchmark["message"])

    def test_market_context_recovers_budget_and_purchaser_from_notice_text(self) -> None:
        first = replace(
            _notice(),
            id="text-1",
            purchaser="",
            core_content="",
            content_text=(
                "项目名称：服务器采购。预算金额：0.000000 万元（人民币） "
                "最高限价：160.000000 万元（人民币）。"
                "采购人信息 名 称：华东数据中心 地址：上海市。"
            ),
            fields={"structured_fields": {}, "evidence": {"quality_score": 0.9}},
        )
        second = replace(
            _notice(),
            id="text-2",
            purchaser="",
            core_content="",
            content_text=(
                "项目名称：服务器扩容。预算总金额（元）： 1,200,000.00。"
                "采购人信息 采购人：华东数据中心 采购经办人：李老师。"
            ),
            fields={"structured_fields": {}, "evidence": {"quality_score": 0.9}},
        )

        market = build_market_context([first, second], as_of=datetime(2026, 8, 15, 10, 0))
        intelligence = analyze_opportunity_payload(
            {
                "title": first.title,
                "content_text": first.content_text,
                "structured_fields": {},
            },
            as_of=datetime(2026, 8, 15, 10, 0),
        )

        self.assertEqual(market["budget_sample_count"], 2)
        self.assertEqual(market["budget"]["median_cny"], 1_400_000)
        self.assertEqual(
            market["top_purchasers"][0], {"name": "华东数据中心", "count": 2}
        )
        self.assertNotIn("预算", intelligence["missing_fields"])
        self.assertNotIn("采购人", intelligence["missing_fields"])

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
                medical = replace(
                    notice,
                    id="n2",
                    title="上海某医院医疗设备采购公开招标公告",
                    source_url="https://www.ccgp.gov.cn/detail/n2.htm",
                    content_text="项目编号 SH-2026-002，医疗器械采购预算 80 万元。",
                    core_content="医疗设备采购，预算 80 万元。",
                )
                conn.execute(
                    """
                    INSERT INTO notices(
                        id, source_site, source_url, canonical_url, title, publish_time,
                        region, purchaser, content_text, core_content, attachments_json, fields_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ccgp:n2",
                        medical.source_site,
                        medical.source_url,
                        medical.source_url,
                        medical.title,
                        medical.publish_time,
                        medical.region,
                        medical.purchaser,
                        medical.content_text,
                        medical.core_content,
                        json_dumps([]),
                        json_dumps(medical.fields),
                    ),
                )

            payload = list_opportunities(settings, limit=10)
            filtered = list_opportunities(settings, limit=10, topic="服务器")

        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(payload["summary"]["market"]["notice_count"], 2)
        categories = payload["summary"]["market"]["available_categories"]
        self.assertEqual({item["name"] for item in categories}, {"服务器", "医疗设备"})
        self.assertEqual(filtered["summary"]["total"], 1)
        self.assertEqual(filtered["summary"]["market"]["notice_count"], 1)
        self.assertEqual(filtered["summary"]["market"]["selected_category"], "服务器")
        self.assertEqual(filtered["items"][0]["notice_id"], "ccgp:n1")
        self.assertTrue(filtered["items"][0]["intelligence"]["project_target"])


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


def _market_notice(notice_id: str, budget: str, purchaser: str) -> Notice:
    notice = _notice()
    structured = dict(notice.fields["structured_fields"])
    structured["budget"] = budget
    structured["purchaser"] = purchaser
    return replace(
        notice,
        id=notice_id,
        title=f"{purchaser}服务器采购项目",
        purchaser=purchaser,
        fields={**notice.fields, "structured_fields": structured},
    )


if __name__ == "__main__":
    unittest.main()
