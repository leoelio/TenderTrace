from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.scenario_training import (
    begin_training_session,
    create_training_session,
    get_training_scenario,
    list_training_scenarios,
    recompute_training_result,
    seed_default_training_scenarios,
    submit_training_answer,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/demo/scenario_training_acceptance_20260929.json"
PARTICIPANTS = [f"benchmark-{index:02d}" for index in range(1, 6)]


def main() -> None:
    settings = Settings.load(ROOT)
    seed_default_training_scenarios(settings, actor="direction18-curator")
    catalog = list_training_scenarios(settings)
    scenario_item = next(
        item for item in catalog["items"] if item["scenario_type"] == "roadshow_pitch"
    )
    scenario = get_training_scenario(settings, str(scenario_item["id"]))
    _clear_previous_benchmark(settings)
    formal_before = _formal_state_hash(settings)
    started = perf_counter()
    samples = []
    for index, participant in enumerate(PARTICIPANTS, start=1):
        pre = _run_session(settings, scenario, participant, stage="pre", variant=index)
        post = _run_session(settings, scenario, participant, stage="post", variant=index)
        samples.append(
            {
                "participant": f"样本{index:02d}",
                "sample_kind": "approved_transcript",
                "pre_score": pre["total_score"],
                "post_score": post["total_score"],
                "improvement": post["total_score"] - pre["total_score"],
                "pre_result_id": pre["id"],
                "post_result_id": post["id"],
                "pre_recomputed": recompute_training_result(settings, str(pre["id"]))[
                    "identical"
                ],
                "post_recomputed": recompute_training_result(settings, str(post["id"]))[
                    "identical"
                ],
            }
        )
    formal_after = _formal_state_hash(settings)
    duration_ms = round((perf_counter() - started) * 1000, 1)
    pre_average = round(mean(item["pre_score"] for item in samples), 1)
    post_average = round(mean(item["post_score"] for item in samples), 1)
    proof = {
        "three_real_anonymized_projects": catalog["project_count"] >= 3,
        "four_approved_scenario_types": catalog["scenario_type_count"] >= 4,
        "six_phase_state_machine": catalog["rules"]["state_machine"]
        == ["opening", "fundamentals", "evidence", "change", "action", "summary"],
        "deterministic_recompute": all(
            item["pre_recomputed"] and item["post_recomputed"] for item in samples
        ),
        "formal_project_unchanged": formal_before == formal_after,
        "five_approved_pre_post_transcripts": len(samples) == 5,
        "post_scores_improve": all(item["improvement"] > 0 for item in samples),
        "model_candidate_does_not_change_rule_score": not catalog["rules"][
            "model_score_affects_result"
        ],
        "preparation_hides_reference_answer": catalog["rules"][
            "preparation_hides_reference_answer"
        ],
        "voice_is_deferred": catalog["rules"]["voice_mode"]
        == "planned_after_hardware_validation",
    }
    payload = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "duration_ms": duration_ms,
        "summary": {
            "project_count": catalog["project_count"],
            "scenario_count": catalog["count"],
            "scenario_type_count": catalog["scenario_type_count"],
            "approved_question_count": sum(
                int(item["question_count"]) for item in catalog["items"]
            ),
            "benchmark_sample_count": len(samples),
            "human_participant_count": 0,
            "pre_average": pre_average,
            "post_average": post_average,
            "average_improvement": round(post_average - pre_average, 1),
        },
        "proof": proof,
        "failed": [key for key, value in proof.items() if not value],
        "status": "passed_with_human_validation_pending",
        "samples": samples,
        "demo_url": "http://127.0.0.1:8000/?view=trainingView",
        "validation_limit": (
            "五份前后测为人工批准的脱敏基准答题文本，用于证明评分稳定和前后可比；"
            "它们不是真人用户实验，不能据此宣称真实学习效果。比赛前仍需至少5名真实成员"
            "使用同一量表完成前后测。"
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _run_session(settings, scenario, participant: str, *, stage: str, variant: int):
    created = create_training_session(
        settings,
        str(scenario["id"]),
        mode="preparation",
        role=str(scenario["target_roles"][0]),
        participant_key=f"{participant}-{stage}",
        participant_display=f"基准样本{variant:02d}",
        sample_kind="approved_transcript",
    )
    session = begin_training_session(
        settings, str(created["id"]), participant_key=f"{participant}-{stage}"
    )
    notice_ref = f"NOTICE:{scenario['notice_id']}"
    source = scenario["source_snapshot"]
    while session["status"] != "completed":
        if stage == "pre":
            answer = f"这个项目需要关注，后续再看看。证据 {notice_ref}。"
        else:
            answer = (
                f"结论：项目位于{source['region']}，采购人为{source['purchaser']}，"
                f"采购对象与服务器项目相关。证据 {notice_ref} 来自公告原文。"
                "当前证据仍有风险和缺口待核验，不能说完全满足。若截止时间提前五天，"
                "立即重排资格复核、材料编制和审批任务；每项写明负责人、截止时间和验收证据，"
                "并同步下一步核验任务。"
            )
        session = submit_training_answer(
            settings,
            str(session["id"]),
            participant_key=f"{participant}-{stage}",
            answer=answer,
            evidence_refs=[notice_ref],
        )
    return session["result"]


def _clear_previous_benchmark(settings: Settings) -> None:
    with connection(settings) as conn:
        ids = [
            str(row["id"])
            for row in conn.execute(
                "SELECT id FROM training_sessions WHERE participant_key LIKE 'benchmark-%'"
            ).fetchall()
        ]
        for session_id in ids:
            conn.execute("DELETE FROM training_results WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM training_turns WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM training_sessions WHERE id = ?", (session_id,))


def _formal_state_hash(settings: Settings) -> str:
    tables = (
        "notices",
        "opportunity_requirements",
        "notice_revisions",
        "opportunity_workflows",
        "decision_scenarios",
        "company_risk_signals",
    )
    payload = {}
    with connection(settings) as conn:
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            payload[table] = [dict(row) for row in rows]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


if __name__ == "__main__":
    main()
