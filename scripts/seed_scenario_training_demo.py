from __future__ import annotations

import json
from pathlib import Path

from tendertrace.config import Settings
from tendertrace.scenario_training import (
    list_training_scenarios,
    seed_default_training_scenarios,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/demo/scenario_training_live_demo_20260929.json"


def main() -> None:
    settings = Settings.load(ROOT)
    seeded = seed_default_training_scenarios(settings, actor="direction18-curator")
    catalog = list_training_scenarios(settings)
    payload = {
        "demo_url": "http://127.0.0.1:8000/?view=trainingView",
        "seeded": seeded,
        "summary": {
            "scenario_count": catalog["count"],
            "project_count": catalog["project_count"],
            "scenario_type_count": catalog["scenario_type_count"],
            "question_count": sum(int(item["question_count"]) for item in catalog["items"]),
            "scoring_version": catalog["rules"]["scoring_version"],
        },
        "scenarios": [
            {
                "id": item["id"],
                "title": item["title"],
                "project_alias": item["project_alias"],
                "scenario_type": item["scenario_type"],
                "notice_id": item["notice_id"],
                "source_url": item["source_url"],
                "roles": item["target_roles"],
                "question_count": item["question_count"],
                "approved_by": item["approved_by"],
                "real_notice": item["source_snapshot"].get("real_notice"),
                "anonymized_for_training": item["source_snapshot"].get(
                    "anonymized_for_training"
                ),
            }
            for item in catalog["items"]
        ],
        "rules": catalog["rules"],
        "interpretation_boundary": (
            "训练场景读取真实公告快照；模拟变化、回答和评分只写训练对象，"
            "不会写回正式项目、人工决策、能力确认或合作方结论。"
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
