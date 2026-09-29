from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from tendertrace.bid_workplan import (
    build_bid_workplan,
    complete_bid_task,
    confirm_requirement,
    export_bid_workplan,
    get_bid_workplan,
    merge_requirements,
    split_requirement,
    upsert_pricing_item,
)
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.digital_twin import build_digital_twin
from tendertrace.integrations.feishu_requirement_sync import (
    sync_bid_workplan_task_status,
    sync_bid_workplan_to_feishu,
)
from tendertrace.opportunity_requirements import upsert_requirement


class BidWorkplanTests(unittest.TestCase):
    def test_api_exposes_confirm_build_complete_and_export_flow(self) -> None:
        from fastapi.testclient import TestClient
        from tendertrace.app.api import create_app
        import os

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous_db = os.environ.get("TENDERTRACE_DB_PATH")
            previous_scheduler = os.environ.get("TENDERTRACE_SCHEDULER_ENABLED")
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "api.sqlite3")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                settings = Settings.load()
                init_db(settings)
                _insert_notice(settings)
                requirement = _requirement(settings, "QUAL-API", "qualification", "pending")
                client = TestClient(create_app())
                confirmed = client.post(f"/api/opportunities/notice-bid-1/requirements/{requirement.id}/confirm", json={"actor": "api-test"})
                built = client.post("/api/opportunities/notice-bid-1/bid-workplan/build", json={"actor": "api-test"})
                task_id = next(item["id"] for item in built.json()["tasks"] if item["requirement_id"] == requirement.id)
                completed = client.post(f"/api/opportunities/notice-bid-1/bid-workplan/tasks/{task_id}/complete", json={"actor": "api-test"})
                exported = client.get("/api/opportunities/notice-bid-1/bid-workplan/export")
            finally:
                if previous_db is None:
                    os.environ.pop("TENDERTRACE_DB_PATH", None)
                else:
                    os.environ["TENDERTRACE_DB_PATH"] = previous_db
                if previous_scheduler is None:
                    os.environ.pop("TENDERTRACE_SCHEDULER_ENABLED", None)
                else:
                    os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = previous_scheduler

        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(built.status_code, 200)
        self.assertEqual(completed.status_code, 200)
        self.assertGreater(completed.json()["summary"]["execution_readiness"], 0)
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.headers["content-type"], "application/zip")

    def test_only_confirmed_requirements_create_formal_plan_and_export_keeps_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            confirmed = _requirement(settings, "QUAL-01", "qualification", "confirmed")
            pending = _requirement(settings, "DISQ-01", "disqualification", "pending")

            plan = build_bid_workplan(settings, "notice-bid-1", actor="tester")

            self.assertEqual(plan["summary"]["confirmed_count"], 1)
            self.assertTrue(plan["tasks"])
            linked_ids = {item["requirement_id"] for item in plan["deliverables"]}
            self.assertEqual(linked_ids, {confirmed.id})
            self.assertNotIn(pending.id, linked_ids)
            export_path = export_bid_workplan(settings, "notice-bid-1")
            with ZipFile(export_path) as archive:
                names = set(archive.namelist())
                payload = json.loads(archive.read("feishu_bitable_rows.json"))
            self.assertIn("03_RACI责任矩阵.csv", names)
            self.assertIn("05_缺口清单.csv", names)
            self.assertEqual({item["requirement_id"] for item in payload["deliverables"]}, {confirmed.id})
            self.assertTrue(all(item["requirement_id"] == confirmed.id for item in payload["raci"]))

    def test_confirm_split_merge_and_edit_history_are_traceable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            parent = _requirement(settings, "TECH-01", "technical", "pending")

            confirm_requirement(settings, "notice-bid-1", parent.id, actor="reviewer")
            children = split_requirement(
                settings,
                "notice-bid-1",
                parent.id,
                [{"title": "接口性能响应"}, {"title": "安全能力响应"}],
                actor="reviewer",
            )
            merged = merge_requirements(
                settings,
                "notice-bid-1",
                [children[0]["id"], children[1]["id"]],
                requirement_key="TECH-MERGED",
                title="技术综合响应",
                actor="reviewer",
            )
            plan = get_bid_workplan(settings, "notice-bid-1")

            self.assertEqual(merged["status"], "confirmed")
            self.assertEqual([item["requirement_key"] for group in plan["requirement_tree"] for item in group["items"]], ["TECH-MERGED"])
            actions = {item["action"] for item in plan["history"]}
            self.assertTrue({"created", "confirmed", "split", "merged"}.issubset(actions))
            self.assertTrue(all(child["parent_requirement_id"] == parent.id for child in children))

    def test_task_completion_flows_to_requirement_and_digital_twin_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            requirement = _requirement(settings, "COMM-01", "commercial", "confirmed")
            before = build_bid_workplan(settings, "notice-bid-1", actor="tester")
            preparation = next(item for item in before["tasks"] if item["requirement_id"] == requirement.id)
            twin_before = build_digital_twin(settings, "notice-bid-1")

            after = complete_bid_task(settings, "notice-bid-1", preparation["id"], actor="tester")
            twin_after = build_digital_twin(settings, "notice-bid-1")

            self.assertGreater(after["summary"]["execution_readiness"], before["summary"]["execution_readiness"])
            self.assertEqual(next(item for item in after["deliverables"] if item["requirement_id"] == requirement.id)["status"], "completed")
            self.assertGreater(
                next(item for item in twin_after["scores"]["bid_readiness"]["components"] if item["key"] == "execution")["score"],
                next(item for item in twin_before["scores"]["bid_readiness"]["components"] if item["key"] == "execution")["score"],
            )

    def test_pricing_summary_is_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            requirement = _requirement(settings, "COMM-01", "commercial", "confirmed")
            upsert_pricing_item(
                settings,
                "notice-bid-1",
                item_key="PRICE-01",
                title="平台许可",
                requirement_id=requirement.id,
                quantity=2,
                unit_price=100,
                cost=120,
                tax_rate=6,
                status="approved",
            )
            summary = get_bid_workplan(settings, "notice-bid-1")["pricing_summary"]
            self.assertEqual(summary["quoted_total"], 200)
            self.assertEqual(summary["estimated_cost"], 120)
            self.assertEqual(summary["gross_margin"], 40)

    def test_feishu_workplan_sync_is_idempotent_and_completion_writes_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp), calendar=True)
            _insert_notice(settings)
            requirement = _requirement(settings, "ATTACH-01", "attachment", "confirmed")
            plan = build_bid_workplan(settings, "notice-bid-1", actor="tester")
            fake = _FakeFeishu()

            first = sync_bid_workplan_to_feishu(settings, "notice-bid-1", client=fake)
            second = sync_bid_workplan_to_feishu(settings, "notice-bid-1", client=fake)
            preparation = next(item for item in plan["tasks"] if item["requirement_id"] == requirement.id)
            fake.completed_guids.add(f"task-{preparation['id']}")
            status = sync_bid_workplan_task_status(settings, "notice-bid-1", client=fake)
            refreshed = get_bid_workplan(settings, "notice-bid-1")

            self.assertEqual(first["created_count"], len(plan["tasks"]))
            self.assertEqual(second["created_count"], 0)
            self.assertEqual(second["skipped_count"], len(plan["tasks"]))
            self.assertEqual(status["completed_count"], 1)
            self.assertEqual(next(item for item in refreshed["tasks"] if item["id"] == preparation["id"])["status"], "completed")


class _FakeFeishu:
    def __init__(self) -> None:
        self.completed_guids: set[str] = set()
        self.calendar_keys: set[str] = set()

    def create_task(self, *, summary, description, client_token, due_timestamp_ms, assignee_open_id):
        # The caller stores the result; tests recover ids through the database-generated token mapping below.
        return {"data": {"task": {"guid": f"task-{_task_id_from_summary(summary, description)}"}}}

    def create_calendar_event(self, *, calendar_id, summary, description, start_timestamp, end_timestamp, idempotency_key):
        self.calendar_keys.add(idempotency_key)
        return {"data": {"event": {"event_id": idempotency_key[:12]}}}

    def get_task(self, task_guid):
        return {"data": {"task": {"completed_at": "2026-09-27T12:00:00Z" if task_guid in self.completed_guids else ""}}}


def _task_id_from_summary(summary: str, description: str) -> str:
    # Description carries the stable task key, but the database id is not exposed to the fake.
    task_key = next(line.split("：", 1)[1] for line in description.splitlines() if line.startswith("作战图任务："))
    return __import__("hashlib").sha256(f"notice-bid-1|task|{task_key}".encode()).hexdigest()[:24]


def _settings(root: Path, *, calendar: bool = False) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n"
        "TENDERTRACE_SCHEDULER_ENABLED=false\n"
        f"FEISHU_CALENDAR_ID={'calendar-test' if calendar else ''}\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    fields = {"structured_fields": {"project_no": "BID-001", "budget": "100万元", "bid_deadline": "2026-10-20 17:00"}}
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title, purchaser, region, content_text, fields_json, updated_at, last_seen_at)
            VALUES ('notice-bid-1', 'ccgp', 'https://example.com/bid-1', 'https://example.com/bid-1', '智能平台采购', '采购中心', '北京', '投标截止时间2026年10月20日17:00。', ?, datetime('now'), datetime('now'))
            """,
            (json.dumps(fields, ensure_ascii=False),),
        )


def _requirement(settings: Settings, key: str, requirement_type: str, status: str):
    return upsert_requirement(
        settings,
        notice_id="notice-bid-1",
        requirement_key=key,
        requirement_type=requirement_type,
        title=f"{key} 测试要求",
        evidence_text="投标人须提供可核验材料，否则投标无效。",
        source_url="https://example.com/bid-1",
        source_locator="招标文件第 3 页 2.1 条",
        mandatory=True,
        confidence=95,
        status=status,
        actor="test",
    )


if __name__ == "__main__":
    unittest.main()
