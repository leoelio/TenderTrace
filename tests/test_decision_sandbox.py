from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.decision_sandbox import (
    compare_scenarios,
    decide_scenario_suggestion,
    formal_project_state_hash,
    promote_scenario,
    recompute_scenario,
    simulate_scenario,
)
from tendertrace.opportunity_requirements import upsert_requirement


class DecisionSandboxTests(unittest.TestCase):
    def test_scenarios_are_isolated_reproducible_comparable_and_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_project(settings)
            formal_before = formal_project_state_hash(settings, NOTICE_ID)

            deadline = simulate_scenario(
                settings,
                NOTICE_ID,
                name="截止提前三天",
                params={"deadline_shift_days": -3},
                actor="项目负责人",
            )
            partner = simulate_scenario(
                settings,
                NOTICE_ID,
                name="伙伴材料补齐",
                params={
                    "scenario_mode": "joint_bid",
                    "partner_material_status": "complete",
                    "delivery_region_status": "covered",
                },
                actor="项目负责人",
            )

            self.assertEqual(formal_project_state_hash(settings, NOTICE_ID), formal_before)
            self.assertFalse(deadline["output"]["formal_write_performed"])
            self.assertNotIn("win_probability", json.dumps(deadline, ensure_ascii=False))
            self.assertFalse(deadline["output"]["uncertainty"]["sufficient_for_probability"])
            self.assertTrue(deadline["output"]["affected_requirements"])
            self.assertTrue(
                all(item.get("input") and item.get("reason") and item.get("rule")
                    for item in deadline["output"]["score_changes"])
            )

            repeated = recompute_scenario(settings, NOTICE_ID, deadline["id"])
            self.assertTrue(repeated["identical"])
            self.assertTrue(repeated["baseline_is_current"])
            comparison = compare_scenarios(settings, NOTICE_ID, deadline["id"], partner["id"])
            self.assertTrue(comparison["no_win_probability"])
            self.assertEqual(len(comparison["metrics"]), 3)
            self.assertTrue(comparison["interpretation"])

    def test_pending_suggestion_needs_human_decision_before_formal_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_project(settings)
            scenario = simulate_scenario(
                settings,
                NOTICE_ID,
                name="人员减少",
                params={"available_people_delta": -2},
                actor="项目负责人",
            )
            formal_before = formal_project_state_hash(settings, NOTICE_ID)
            suggestion = promote_scenario(
                settings, NOTICE_ID, scenario["id"], actor="项目负责人"
            )
            self.assertEqual(suggestion["status"], "pending")
            self.assertEqual(formal_project_state_hash(settings, NOTICE_ID), formal_before)

            accepted = decide_scenario_suggestion(
                settings,
                NOTICE_ID,
                suggestion["id"],
                accept=True,
                actor="投标总监",
                note="确认纳入正式计划",
            )
            self.assertEqual(accepted["status"], "accepted")
            self.assertTrue(accepted["created_task_ids"])
            self.assertNotEqual(formal_project_state_hash(settings, NOTICE_ID), formal_before)
            with connection(settings) as conn:
                task = conn.execute(
                    "SELECT milestone_type, formal FROM bid_plan_tasks WHERE id = ?",
                    (accepted["created_task_ids"][0],),
                ).fetchone()
            self.assertEqual(task["milestone_type"], "sandbox_suggestion")
            self.assertEqual(task["formal"], 1)

    def test_rejected_suggestion_never_creates_formal_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_project(settings)
            scenario = simulate_scenario(
                settings,
                NOTICE_ID,
                name="区域不覆盖",
                params={"delivery_region_status": "uncovered"},
                actor="项目负责人",
            )
            suggestion = promote_scenario(settings, NOTICE_ID, scenario["id"], actor="项目负责人")
            formal_before = formal_project_state_hash(settings, NOTICE_ID)
            rejected = decide_scenario_suggestion(
                settings,
                NOTICE_ID,
                suggestion["id"],
                accept=False,
                actor="投标总监",
                note="暂不采用该方案",
            )
            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(rejected["created_task_ids"], [])
            self.assertEqual(formal_project_state_hash(settings, NOTICE_ID), formal_before)

    def test_api_supports_complete_sandbox_flow(self) -> None:
        from fastapi.testclient import TestClient
        from tendertrace.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {
                "TENDERTRACE_DB_PATH": os.environ.get("TENDERTRACE_DB_PATH"),
                "TENDERTRACE_SCHEDULER_ENABLED": os.environ.get("TENDERTRACE_SCHEDULER_ENABLED"),
            }
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "api.sqlite3")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                settings = Settings.load()
                init_db(settings)
                _seed_project(settings)
                client = TestClient(create_app())
                baseline = client.get(f"/api/opportunities/{NOTICE_ID}/decision-sandbox")
                created = client.post(
                    f"/api/opportunities/{NOTICE_ID}/decision-sandbox/scenarios",
                    json={
                        "name": "联合投标",
                        "actor": "项目负责人",
                        "params": {"scenario_mode": "joint_bid", "partner_material_status": "complete"},
                    },
                )
                scenario_id = created.json()["id"]
                recomputed = client.post(
                    f"/api/opportunities/{NOTICE_ID}/decision-sandbox/scenarios/{scenario_id}/recompute"
                )
                promoted = client.post(
                    f"/api/opportunities/{NOTICE_ID}/decision-sandbox/scenarios/{scenario_id}/promote",
                    json={"actor": "项目负责人"},
                )
                suggestion_id = promoted.json()["id"]
                decided = client.post(
                    f"/api/opportunities/{NOTICE_ID}/decision-sandbox/suggestions/{suggestion_id}/decision",
                    json={"accept": True, "actor": "投标总监", "note": "同意进入正式计划"},
                )
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(baseline.status_code, 200)
        self.assertTrue(baseline.json()["rules"]["formal_data_is_read_only"])
        self.assertEqual(created.status_code, 200)
        self.assertEqual(recomputed.status_code, 200)
        self.assertTrue(recomputed.json()["identical"])
        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(promoted.json()["status"], "pending")
        self.assertEqual(decided.status_code, 200)
        self.assertEqual(decided.json()["status"], "accepted")


NOTICE_ID = "notice-sandbox-1"


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed_project(settings: Settings) -> None:
    today = date.today()
    fields = {
        "structured_fields": {
            "project_no": "TT-SANDBOX-001",
            "budget": 5000000,
            "bid_deadline": (today + timedelta(days=20)).isoformat(),
        }
    }
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json,
                updated_at, last_seen_at
            ) VALUES (?, 'ccgp', ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                NOTICE_ID,
                "https://example.com/sandbox",
                "https://example.com/sandbox",
                "政务云平台采购项目",
                "示例采购中心",
                today.isoformat(),
                "北京",
                "政务云平台采购项目，预算500万元，含技术、资格与交付要求。",
                "建设政务云平台并完成本地交付。",
                json.dumps(fields, ensure_ascii=False),
            ),
        )
        conn.execute(
            """
            INSERT INTO opportunity_team_members(
                id, notice_id, member_key, member_open_id, member_name, role
            ) VALUES ('member-sandbox-1', ?, 'project-manager', 'ou-sandbox-1', '项目经理', 'bid_manager')
            """,
            (NOTICE_ID,),
        )
    for key, requirement_type, title in (
        ("DEADLINE-01", "deadline", "投标截止时间"),
        ("TECH-01", "technical", "关键技术参数"),
        ("QUAL-01", "qualification", "伙伴专项授权"),
        ("COMM-01", "commercial", "区域交付承诺"),
    ):
        upsert_requirement(
            settings,
            notice_id=NOTICE_ID,
            requirement_key=key,
            requirement_type=requirement_type,
            title=title,
            evidence_text=f"采购文件要求：{title}",
            source_url="https://example.com/sandbox",
            source_locator=f"采购文件/{key}",
            mandatory=True,
            confidence=96,
            status="confirmed",
            actor="seed",
        )


if __name__ == "__main__":
    unittest.main()
