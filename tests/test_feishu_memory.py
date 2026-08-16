from __future__ import annotations

import unittest

from tendertrace.integrations.feishu_memory import build_memory_weekly_card


class FeishuMemoryCardTests(unittest.TestCase):
    def test_card_contains_live_metrics_evidence_and_feedback_actions(self) -> None:
        report = {
            "user_id": "admin",
            "period": {"from": "2026-08-10", "to": "2026-08-16"},
            "summary": {
                "runs_finished": 3,
                "downloads": 2,
                "subscriptions_created": 1,
            },
            "knowledge_coverage": {
                "active_count": 1,
                "topics": [{"name": "服务器", "count": 1}],
                "regions": [{"name": "上海", "count": 1}],
            },
            "generated_advice": {
                "headline": "本周有 2 个 A 级机会需要优先分派",
                "summary": "数据来自本周机会库。",
            },
            "recommendation_plan": [
                {
                    "id": "advice-1",
                    "title": "分派并复核 2 个 A 级机会",
                    "reason": "达到优先跟进阈值。",
                    "action": "确认负责人和下一步动作。",
                    "feedback_status": "pending",
                }
            ],
        }

        card = build_memory_weekly_card(report)
        card_text = str(card)

        self.assertIn("完成运行", card_text)
        self.assertIn("分派并复核 2 个 A 级机会", card_text)
        self.assertIn("memory_advice_accept", card_text)
        self.assertIn("memory_advice_complete", card_text)
        self.assertIn("智能采集", card_text)
        self.assertIn("advice-1", card_text)


if __name__ == "__main__":
    unittest.main()
