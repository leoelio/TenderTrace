from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from tendertrace.requirement_extraction import _candidates


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs" / "demo" / "direction4_requirement_gold_cases.json"
OUTPUT = ROOT / "docs" / "demo" / "direction4_bid_workplan_acceptance_20260927.json"
HIGH_VALUE_TYPES = ("qualification", "deadline", "scoring", "disqualification", "attachment")


def evaluate() -> dict[str, object]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    totals = defaultdict(lambda: {"gold": 0, "predicted": 0, "matched": 0})
    cases = []
    for case in fixture["cases"]:
        predicted = [
            item
            for item in _candidates(
                [
                    {
                        "text": case["text"],
                        "source_url": case["source_url"],
                        "source_locator": case["source_locator"],
                        "source_revision_id": f"gold:{case['case_id']}",
                    }
                ]
            )
            if item["requirement_type"] in HIGH_VALUE_TYPES
        ]
        gold = case["gold"]
        matched_predicted: set[int] = set()
        matched_gold: set[int] = set()
        for gold_index, expected in enumerate(gold):
            for predicted_index, actual in enumerate(predicted):
                if predicted_index in matched_predicted:
                    continue
                if actual["requirement_type"] != expected["type"]:
                    continue
                if _normalize(actual["evidence_text"]) == _normalize(expected["text"]):
                    matched_predicted.add(predicted_index)
                    matched_gold.add(gold_index)
                    break
        for requirement_type in HIGH_VALUE_TYPES:
            totals[requirement_type]["gold"] += sum(item["type"] == requirement_type for item in gold)
            totals[requirement_type]["predicted"] += sum(item["requirement_type"] == requirement_type for item in predicted)
            totals[requirement_type]["matched"] += sum(
                gold[index]["type"] == requirement_type for index in matched_gold
            )
        cases.append(
            {
                "case_id": case["case_id"],
                "source_url": case["source_url"],
                "gold_count": len(gold),
                "predicted_count": len(predicted),
                "matched_count": len(matched_gold),
                "human_correction_count": len(gold) - len(matched_gold) + len(predicted) - len(matched_predicted),
                "unmatched_gold": [gold[index] for index in range(len(gold)) if index not in matched_gold],
                "extra_predictions": [predicted[index] for index in range(len(predicted)) if index not in matched_predicted],
            }
        )
    by_type = {}
    for requirement_type in HIGH_VALUE_TYPES:
        values = totals[requirement_type]
        precision = values["matched"] / values["predicted"] if values["predicted"] else 0
        recall = values["matched"] / values["gold"] if values["gold"] else 0
        by_type[requirement_type] = {
            **values,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "human_correction_count": values["gold"] + values["predicted"] - 2 * values["matched"],
        }
    result = {
        "evaluated_at": "2026-09-27",
        "fixture": str(FIXTURE.relative_to(ROOT)).replace("\\", "/"),
        "case_count": len(cases),
        "scope": list(HIGH_VALUE_TYPES),
        "by_type": by_type,
        "cases": cases,
        "guardrails": {
            "deadline_and_disqualification_require_human_confirmation": True,
            "no_text_fallback": "ocr_or_manual_required; no structured requirements are fabricated",
        },
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _normalize(value: str) -> str:
    return "".join(str(value).split()).strip("，,。；;")


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
