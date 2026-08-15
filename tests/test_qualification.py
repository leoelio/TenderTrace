from __future__ import annotations

from datetime import date
import unittest

from tendertrace.qualification import action_blockers, assess_qualification


class QualificationAssessmentTests(unittest.TestCase):
    def test_complete_opportunity_is_ready_for_go_decision(self) -> None:
        assessment = assess_qualification(
            _opportunity(),
            {"owner_name": "张三"},
            as_of=date(2026, 8, 16),
        )

        self.assertEqual(assessment.status, "ready")
        self.assertEqual(assessment.recommended_decision, "go")
        self.assertEqual(assessment.blockers["approve_bid"], ())
        self.assertTrue(all(gate.status == "passed" for gate in assessment.gates[:-1]))

    def test_missing_owner_and_purchaser_block_progression(self) -> None:
        opportunity = _opportunity()
        opportunity["purchaser"] = ""

        assessment = assess_qualification(
            opportunity,
            {},
            as_of=date(2026, 8, 16),
        )
        payload = assessment.to_dict()

        self.assertEqual(assessment.status, "blocked")
        self.assertEqual(assessment.recommended_decision, "hold")
        self.assertEqual(action_blockers(payload, "pursue"), ["机会负责人", "采购主体"])

    def test_expired_deadline_recommends_no_go(self) -> None:
        opportunity = _opportunity()
        opportunity["bid_deadline"] = "2026-08-15 17:00"

        assessment = assess_qualification(
            opportunity,
            {"owner_name": "张三"},
            as_of=date(2026, 8, 16),
        )

        self.assertEqual(assessment.status, "blocked")
        self.assertEqual(assessment.recommended_decision, "no_go")
        self.assertIn("投标窗口", assessment.blockers["approve_bid"])


def _opportunity() -> dict[str, object]:
    return {
        "purchaser": "示例采购人",
        "bid_deadline": "2026-08-30 17:00",
        "intelligence": {
            "score": 82,
            "scores": {"credibility": 85, "completeness": 78},
            "requirement_review": {"coverage_score": 70},
        },
    }


if __name__ == "__main__":
    unittest.main()
