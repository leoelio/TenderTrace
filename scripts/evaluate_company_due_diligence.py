from __future__ import annotations

import json
from pathlib import Path

from tendertrace.config import Settings
from tendertrace.db import connection


ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "docs" / "demo" / "company_due_diligence_gold_cases_20260929.json"
OUTPUT_PATH = ROOT / "docs" / "demo" / "company_due_diligence_acceptance_20260929.json"


def main() -> None:
    settings = Settings.load(ROOT)
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    true_positive = false_negative = false_positive = true_negative = 0
    case_results = []
    with connection(settings) as conn:
        for case in gold["cases"]:
            expected = set(case["expected_rules"])
            actual = {
                str(row["rule_key"])
                for row in conn.execute(
                    """
                    SELECT rule_key FROM company_risk_signals
                    WHERE workspace_id = ? AND entity_id = ?
                      AND signal_kind = 'risk' AND signal_status = 'active'
                    """,
                    (case["workspace_id"], case["entity_id"]),
                ).fetchall()
            }
            tp = len(expected & actual)
            fn = len(expected - actual)
            fp = len(actual - expected)
            tn = int(not expected and not actual)
            true_positive += tp
            false_negative += fn
            false_positive += fp
            true_negative += tn
            case_results.append(
                {
                    "case_id": case["case_id"],
                    "expected": sorted(expected),
                    "actual": sorted(actual),
                    "true_positive": tp,
                    "false_negative": fn,
                    "false_positive": fp,
                    "passed": fn == 0 and fp == 0 and bool(case["missing_is_separate"]),
                }
            )
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    false_positive_rate = false_positive / (false_positive + true_negative) if false_positive + true_negative else 0.0
    result = {
        "direction": 16,
        "gold_case_count": len(case_results),
        "true_positive": true_positive,
        "false_negative": false_negative,
        "false_positive": false_positive,
        "true_negative": true_negative,
        "key_risk_recall": round(recall, 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "missing_information_separated": all(item["passed"] for item in case_results),
        "passed": recall == 1.0 and false_positive == 0 and all(item["passed"] for item in case_results),
        "cases": case_results,
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
