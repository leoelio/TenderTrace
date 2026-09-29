from __future__ import annotations

from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.app import api as api_module
from tendertrace.config import Settings
from tendertrace.db import SCHEMA_VERSION, connection, database_health, init_db
from tendertrace.scenario_training import (
    begin_training_session,
    create_training_session,
    get_training_hint,
    get_training_session,
    list_training_scenarios,
    recompute_training_result,
    seed_default_training_scenarios,
    submit_training_answer,
    sync_training_remediation_task,
    team_training_readiness,
)


class FakeFeishu:
    def create_task(self, **kwargs):
        return {"code": 0, "data": {"task": {"guid": "training-task-guid"}}, "request": kwargs}


class ScenarioTrainingTests(unittest.TestCase):
    def test_schema_and_seed_create_three_real_cases_and_four_approved_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            seeded = seed_default_training_scenarios(settings, actor="curator")
            catalog = list_training_scenarios(settings)
            health = database_health(settings)
            with connection(settings) as conn:
                rubric_count = conn.execute("SELECT COUNT(*) FROM training_rubrics").fetchone()[0]

        self.assertEqual(SCHEMA_VERSION, 58)
        self.assertEqual(health["schema_versions"][-1], 58)
        self.assertTrue(
            {
                "training_scenarios",
                "training_sessions",
                "training_turns",
                "training_rubrics",
                "training_results",
            }.issubset(set(health["tables"]))
        )
        self.assertEqual(seeded["scenario_count"], 4)
        self.assertGreaterEqual(seeded["project_count"], 3)
        self.assertEqual(catalog["count"], 4)
        self.assertGreaterEqual(catalog["project_count"], 3)
        self.assertEqual(catalog["scenario_type_count"], 4)
        self.assertEqual(rubric_count, 24)
        self.assertTrue(all(item["approval_status"] == "approved" for item in catalog["items"]))
        self.assertTrue(all(item["question_count"] == 6 for item in catalog["items"]))
        self.assertTrue(catalog["rules"]["formal_project_read_only"])
        self.assertEqual(catalog["rules"]["voice_mode"], "planned_after_hardware_validation")

    def test_state_machine_hints_evidence_followup_and_recompute_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            seed_default_training_scenarios(settings)
            scenario = list_training_scenarios(settings)["items"][0]
            before = _formal_hash(settings)
            created = create_training_session(
                settings,
                str(scenario["id"]),
                mode="learning",
                role=str(scenario["target_roles"][0]),
                participant_key="person-a",
                participant_display="学员甲",
            )
            active = begin_training_session(settings, str(created["id"]), participant_key="person-a")
            hint = get_training_hint(settings, str(created["id"]), participant_key="person-a")
            followed = submit_training_answer(
                settings,
                str(created["id"]),
                participant_key="person-a",
                answer="我们完全满足要求，没有风险。",
            )

            self.assertEqual(active["status"], "active")
            self.assertEqual(active["current_question"]["phase"], "opening")
            self.assertEqual(hint["hint_level"], 1)
            self.assertTrue(followed["turns"][0]["feedback"]["follow_up_required"])
            self.assertTrue(followed["current_question"]["question_id"].endswith(":followup"))
            self.assertEqual(followed["turns"][0]["first_answer"], "我们完全满足要求，没有风险。")

            session = _finish_session(settings, followed, "person-a")
            result = session["result"]
            recomputed = recompute_training_result(settings, str(result["id"]))
            after = _formal_hash(settings)

        self.assertEqual(session["status"], "completed")
        self.assertTrue(result["score_hash"])
        self.assertEqual(len(result["dimension_scores"]), 5)
        self.assertTrue(recomputed["identical"])
        self.assertEqual(before, after)
        self.assertEqual(result["replay"]["formal_project_write_count"], 0)

    def test_preparation_mode_hides_answer_and_low_confidence_model_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            seed_default_training_scenarios(settings)
            scenario = list_training_scenarios(settings)["items"][1]
            created = create_training_session(
                settings,
                str(scenario["id"]),
                mode="preparation",
                role=str(scenario["target_roles"][0]),
                participant_key="person-b",
                participant_display="学员乙",
            )
            active = begin_training_session(settings, str(created["id"]), participant_key="person-b")
            with self.assertRaises(ValueError):
                get_training_hint(settings, str(created["id"]), participant_key="person-b")
            answered = submit_training_answer(
                settings,
                str(created["id"]),
                participant_key="person-b",
                answer="当前证据只能说明采购项目存在，技术边界和验收条件仍需核验。",
                evidence_refs=[f"NOTICE:{scenario['notice_id']}"],
                model_evaluation={"score": 98, "confidence": 45, "rationale": "表达较完整，但置信度不足。"},
            )

        turn = answered["turns"][0]
        self.assertTrue(turn["feedback"]["standard_answer_hidden"])
        self.assertNotIn("reference_facts", turn["feedback"])
        self.assertEqual(turn["model_evaluation"]["status"], "pending_review")
        self.assertFalse(turn["model_evaluation"]["score_affects_result"])
        self.assertEqual(active["mode"], "preparation")

    def test_result_privacy_team_aggregate_and_feishu_task_are_controlled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            seed_default_training_scenarios(settings)
            scenario = list_training_scenarios(settings)["items"][2]
            created = create_training_session(
                settings,
                str(scenario["id"]),
                mode="preparation",
                role=str(scenario["target_roles"][0]),
                participant_key="person-c",
                participant_display="学员丙",
                sample_kind="manual_validation",
            )
            active = begin_training_session(settings, str(created["id"]), participant_key="person-c")
            completed = _finish_session(settings, active, "person-c", weak=True)
            result = completed["result"]
            task = result["remediation_tasks"][0]
            receipt = sync_training_remediation_task(
                settings,
                str(result["id"]),
                str(task["id"]),
                client=FakeFeishu(),
            )
            reused = sync_training_remediation_task(
                settings,
                str(result["id"]),
                str(task["id"]),
                client=FakeFeishu(),
            )
            team = team_training_readiness(settings)
            with self.assertRaises(LookupError):
                get_training_session(settings, str(created["id"]), participant_key="another-person")
            manager = get_training_session(
                settings,
                str(created["id"]),
                participant_key="manager",
                manager=True,
            )

        self.assertEqual(receipt["status"], "created")
        self.assertEqual(receipt["task"]["feishu_task_guid"], "training-task-guid")
        self.assertEqual(reused["status"], "reused")
        self.assertEqual(team["participant_count"], 1)
        self.assertEqual(team["completed_session_count"], 1)
        self.assertTrue(manager["privacy"]["not_for_performance_decision"])

    def test_api_exposes_catalog_session_answer_result_and_team_view(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            with patch.object(api_module.Settings, "load", return_value=settings):
                with TestClient(api_module.create_app()) as client:
                    seeded = client.post("/api/training/scenarios/seed", json={})
                    catalog = client.get("/api/training/scenarios")
                    scenario = catalog.json()["items"][0]
                    created = client.post(
                        "/api/training/sessions",
                        json={
                            "scenario_id": scenario["id"],
                            "mode": "preparation",
                            "role": scenario["target_roles"][0],
                            "participant_key": "api-user",
                        },
                    )
                    session_id = created.json()["id"]
                    begun = client.post(
                        f"/api/training/sessions/{session_id}/begin",
                        json={"participant_key": "api-user"},
                    )
                    answered = client.post(
                        f"/api/training/sessions/{session_id}/answer",
                        json={
                            "participant_key": "api-user",
                            "answer": "当前证据表明项目位于北京，采购内容需继续核验。",
                            "evidence_refs": [f"NOTICE:{scenario['notice_id']}"],
                        },
                    )
                    loaded = client.get(
                        f"/api/training/sessions/{session_id}",
                        params={"participant_key": "api-user"},
                    )
                    history = client.get(
                        "/api/training/sessions", params={"participant_key": "api-user"}
                    )
                    team = client.get("/api/training/team-readiness")

        self.assertEqual(seeded.status_code, 200)
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()["count"], 4)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(begun.status_code, 200)
        self.assertEqual(answered.status_code, 200)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["count"], 1)
        self.assertEqual(team.status_code, 200)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed_notices(settings: Settings) -> None:
    notices = (
        ("train-a", "北京", "金融科技单位", "ARM服务器采购项目", "采购ARM服务器并完成部署。"),
        ("train-b", "上海", "支付清算单位", "服务器设备采购项目", "采购服务器、存储和网络设备。"),
        ("train-c", "全国", "行业协会", "综合服务采购更正公告", "本项目发布更正，截止时间和服务要求需核对。"),
        ("train-d", "四川省", "研究机构", "机架式服务器采购合同", "成交供应商已公布，合作前仍需完成尽调。"),
    )
    with connection(settings) as conn:
        for index, (notice_id, region, purchaser, title, content) in enumerate(notices, start=1):
            conn.execute(
                """
                INSERT INTO notices(
                    id, source_site, source_url, canonical_url, title, publish_time,
                    region, purchaser, content_text, core_content, fields_json
                ) VALUES (?, 'ccgp', ?, ?, ?, '2026-09-20', ?, ?, ?, ?, '{}')
                """,
                (
                    notice_id,
                    f"https://example.com/{notice_id}",
                    f"https://example.com/{notice_id}",
                    title,
                    region,
                    purchaser,
                    content,
                    content,
                ),
            )
            req_id = f"req-{index}"
            conn.execute(
                """
                INSERT INTO opportunity_requirements(
                    id, notice_id, requirement_key, requirement_type, title,
                    evidence_text, source_url, source_locator, mandatory, confidence
                ) VALUES (?, ?, ?, 'technical', '技术与交付要求', ?, ?, '公告正文', 1, 95)
                """,
                (req_id, notice_id, f"R-{index}", content, f"https://example.com/{notice_id}"),
            )
            if notice_id == "train-c":
                conn.execute(
                    """
                    INSERT INTO notice_revisions(
                        id, notice_id, change_hash, changed_fields_json, before_json, after_json
                    ) VALUES ('rev-train-c', 'train-c', 'hash', '["bid_deadline"]',
                              '{"bid_deadline":"2026-10-10"}', '{"bid_deadline":"2026-10-05"}')
                    """
                )


def _finish_session(
    settings: Settings,
    session: dict[str, object],
    participant_key: str,
    *,
    weak: bool = False,
) -> dict[str, object]:
    current = session
    guard = 0
    while current["status"] != "completed":
        guard += 1
        if guard > 20:
            raise AssertionError("training session did not complete")
        if weak:
            answer = "不知道，需要看看。"
            refs = []
        else:
            answer = (
                "结论：当前证据只能支持项目存在。1、引用公告原文；2、核验资格和时间；"
                "3、由负责人在截止前完成复核。风险和缺口尚未确认，下一步同步任务。"
            )
            refs = [f"NOTICE:{current['notice_id']}"]
        current = submit_training_answer(
            settings,
            str(current["id"]),
            participant_key=participant_key,
            answer=answer,
            evidence_refs=refs,
        )
    return current


def _formal_hash(settings: Settings) -> str:
    with connection(settings) as conn:
        payload = {}
        for table in ("notices", "opportunity_requirements", "notice_revisions"):
            rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            payload[table] = [dict(row) for row in rows]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


if __name__ == "__main__":
    unittest.main()
