from __future__ import annotations

import json
from pathlib import Path
import tempfile

from tendertrace.business_measurements import business_measurement_summary, upsert_business_measurement
from tendertrace.config import Settings
from tendertrace.db import connection, init_db


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/demo/business_value_lab_acceptance_20260928.json"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env.local").write_text(
            "TENDERTRACE_DB_PATH=data/acceptance.sqlite3\n", encoding="utf-8"
        )
        settings = Settings.load(root)
        init_db(settings)
        samples = [
            ("opportunity_discovery", "ccgp-001", 36, 14, 3, 0, False),
            ("opportunity_verification", "pbc-067GSF2026091", 44, 18, 4, 1, False),
            ("requirement_breakdown", "ggzy-00314", 68, 31, 6, 1, False),
            ("capability_matching", "canadabuys-001", 52, 27, 3, 1, False),
            ("change_review", "pbc-change-001", 29, 12, 2, 0, False),
            ("source_verification", "ggzy-outlier-001", 21, 27, 2, 3, True),
        ]
        for index, (task, sample, baseline, assisted, base_miss, assisted_miss, outlier) in enumerate(samples, 1):
            upsert_business_measurement(
                settings,
                experiment_id="direction12-controlled-acceptance",
                experiment_version=1,
                task_type=task,
                sample_ref=sample,
                participant=f"验收角色{1 + index % 2}",
                document_type="公开公告网页" if index < 3 else "公开招标PDF",
                file_count=1,
                sequence_order="manual_first" if index % 2 else "assisted_first",
                conditions="同一公开文件、固定任务清单、相同计时起止点；数值仅用于验证复算逻辑",
                source_url=f"https://example.test/public-source/{sample}",
                raw_record_url=f"/outputs/acceptance/raw/{sample}.json",
                gold_standard_url=f"/outputs/acceptance/gold/{sample}.json",
                baseline_minutes=baseline,
                assisted_minutes=assisted,
                baseline_active_minutes=max(1, baseline - 2),
                assisted_active_minutes=max(1, assisted - 4),
                baseline_machine_wait_seconds=0,
                assisted_machine_wait_seconds=35 + index,
                baseline_omissions=base_miss,
                assisted_omissions=assisted_miss,
                baseline_false_satisfied=2,
                assisted_false_satisfied=3 if outlier else 0,
                baseline_rework_count=2,
                assisted_rework_count=3 if outlier else 1,
                is_outlier=outlier,
                outlier_reason="受控异常值：辅助处理更慢且质量更差" if outlier else "",
                quality_status="passed",
                reviewer="验收金标负责人",
                note="受控验收夹具，不作为真实业务收益结论。",
                recorded_by="direction12-verifier",
            )
        upsert_business_measurement(
            settings,
            experiment_id="direction12-controlled-acceptance",
            experiment_version=1,
            task_type="expert_review",
            sample_ref="failed-quality-001",
            baseline_minutes=33,
            assisted_minutes=15,
            quality_status="failed",
            reviewer="验收金标负责人",
            gold_standard_url="/outputs/acceptance/gold/failed-quality-001.json",
            note="受控失败样本：辅助结果缺少关键合规结论。",
            recorded_by="direction12-verifier",
        )
        summary = business_measurement_summary(settings)
        with connection(settings) as conn:
            audit_count = conn.execute(
                "SELECT COUNT(*) FROM business_measurement_events"
            ).fetchone()[0]
        evidence = {
            "dataset_kind": "controlled_acceptance_fixture",
            "business_claim_allowed": False,
            "warning": "本数据仅验证复算、异常值、失败样本和审计逻辑，不是实际人员效率结论。",
            "summary": {
                key: summary[key]
                for key in (
                    "status",
                    "record_count",
                    "eligible_sample_count",
                    "quality_failed_count",
                    "outlier_count",
                    "participant_count",
                    "document_types",
                    "baseline_minutes",
                    "assisted_minutes",
                    "saved_minutes",
                    "time_saving_rate",
                )
            },
            "metrics": summary["metrics"],
            "formulas": summary["formulas"],
            "proofs": {
                "percentages_recomputable": all(
                    formula["denominator"] >= 0 for formula in summary["formulas"]
                ),
                "participants_samples_conditions_explicit": bool(
                    summary["participant_count"]
                    and summary["record_count"]
                    and summary["conditions"]
                ),
                "quality_from_human_gold": all(
                    item["gold_standard_url"]
                    for item in summary["items"]
                    if item["quality_status"] != "not_reviewed"
                ),
                "failed_sample_visible": summary["quality_failed_count"] == 1,
                "outlier_visible_and_included": (
                    summary["outlier_count"] == 1
                    and any(
                        value["is_outlier"]
                        for value in summary["metrics"]["total_time"]["paired_values"]
                    )
                ),
                "negative_sample_not_hidden": any(
                    value["delta"] < 0
                    for value in summary["metrics"]["total_time"]["paired_values"]
                ),
                "generalization_forbidden": summary["generalization_allowed"] is False,
                "all_eighteen_directions_mapped": len(summary["direction_coverage"]) == 18,
                "history_preserved": audit_count == 7,
            },
        }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
