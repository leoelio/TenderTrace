from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import warnings
from unittest.mock import patch


ENV_KEYS = (
    "TENDERTRACE_DB_PATH",
    "TENDERTRACE_OUTPUTS_DIR",
    "TENDERTRACE_OUTBOX_DIR",
    "TENDERTRACE_SNAPSHOTS_DIR",
    "TENDERTRACE_TRACES_DIR",
    "TENDERTRACE_SECRETS_DIR",
    "TENDERTRACE_SCHEDULER_ENABLED",
    "TENDERTRACE_API_TOKEN",
)


class OpportunityApiTests(unittest.TestCase):
    def test_action_endpoint_updates_stage_and_returns_gate_reasons(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module
        from tendertrace.config import Settings
        from tendertrace.db import connection, init_db

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            os.environ["TENDERTRACE_API_TOKEN"] = ""
            try:
                settings = Settings.load()
                init_db(settings)
                with connection(settings) as conn:
                    conn.execute(
                        """
                        INSERT INTO notices(
                            id, source_site, source_url, canonical_url, title, purchaser,
                            publish_time, content_text, fields_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "notice-api-1",
                            "ccgp",
                            "https://example.com/notice-api-1",
                            "https://example.com/notice-api-1",
                            "服务器采购项目",
                            "示例采购人",
                            "2026-08-15",
                            "服务器采购项目，采购人为示例采购人。",
                            '{"bid_deadline":"2026-08-30 17:00"}',
                        ),
                    )
                with patch.object(
                    api_module,
                    "update_opportunity_workflow_in_bitable",
                    return_value=SimpleNamespace(status="skipped"),
                ), patch.object(
                    api_module,
                    "update_opportunity_facts_in_bitable",
                    return_value=SimpleNamespace(status="sent", message=""),
                ), patch.object(
                    api_module,
                    "sync_feishu_tasks",
                    return_value=SimpleNamespace(
                        scanned_count=2,
                        to_dict=lambda: {
                            "status": "finished",
                            "scanned_count": 2,
                            "updated_count": 1,
                            "completed_count": 1,
                            "overdue_count": 0,
                            "completion_notifications_sent": 1,
                            "completion_notifications_skipped": 0,
                            "overdue_notifications_sent": 1,
                            "overdue_notifications_skipped": 0,
                            "failed_count": 0,
                            "failures": [],
                        },
                    ),
                ), patch.object(
                    api_module.FeishuClient,
                    "list_authorized_users",
                    return_value={
                        "status": "ready",
                        "items": [{"open_id": "ou_owner", "name": "测试负责人"}],
                        "returned_count": 1,
                    },
                ):
                    client = TestClient(api_module.create_app())
                    fact_payload = {
                        "facts": {
                            "project_no": "SH-2026-001",
                            "budget": "120 万元",
                            "bid_deadline": "2026-08-30 17:00",
                        },
                        "source_url": "https://example.com/notice-api-1",
                        "evidence_text": "原始公告已核验",
                        "actor": "测试分析师",
                    }
                    facts = client.patch(
                        "/api/opportunities/notice-api-1/facts",
                        json=fact_payload,
                    )
                    duplicate_facts = client.patch(
                        "/api/opportunities/notice-api-1/facts",
                        json=fact_payload,
                    )
                    cors = client.options(
                        "/api/opportunities/notice-api-1/facts",
                        headers={
                            "Origin": "https://open.feishu.cn",
                            "Access-Control-Request-Method": "PATCH",
                        },
                    )
                    claimed = client.post(
                        "/api/opportunities/notice-api-1/actions",
                        json={"action": "claim", "actor_name": "测试负责人"},
                    )
                    blocked = client.post(
                        "/api/opportunities/notice-api-1/actions",
                        json={"action": "prepare_bid", "actor_name": "测试负责人"},
                    )
                    task_sync = client.post(
                        "/api/opportunities/tasks/sync",
                        json={"limit": 100},
                    )
                    users = client.get("/api/integrations/feishu/users?limit=20")
                    escalation = client.post(
                        "/api/opportunities/escalations/send-feishu",
                        json={},
                    )
                    with patch.object(
                        api_module,
                        "send_opportunity_briefing",
                        return_value=SimpleNamespace(
                            status="skipped",
                            artifact_key="",
                            opportunity_count=0,
                            to_dict=lambda: {"status": "skipped", "opportunity_count": 0},
                        ),
                    ):
                        briefing = client.post(
                            "/api/opportunities/briefing/send-feishu",
                            json={},
                        )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(facts.status_code, 200)
        self.assertEqual(facts.json()["bitable_status"], "sent")
        self.assertEqual(facts.json()["opportunity"]["project_no"], "SH-2026-001")
        self.assertEqual(len(facts.json()["audit"]), 1)
        self.assertEqual(duplicate_facts.json()["status"], "unchanged")
        self.assertEqual(duplicate_facts.json()["bitable_status"], "skipped")
        self.assertEqual(len(duplicate_facts.json()["audit"]), 1)
        self.assertEqual(cors.status_code, 200)
        self.assertIn("PATCH", cors.headers["access-control-allow-methods"])
        self.assertEqual(claimed.json()["workflow"]["stage"], "qualifying")
        self.assertEqual(claimed.json()["workflow"]["owner_name"], "测试负责人")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(task_sync.status_code, 200)
        self.assertEqual(task_sync.json()["completed_count"], 1)
        self.assertEqual(task_sync.json()["completion_notifications_sent"], 1)
        self.assertEqual(task_sync.json()["overdue_notifications_sent"], 1)
        self.assertEqual(users.status_code, 200)
        self.assertEqual(users.json()["items"][0]["open_id"], "ou_owner")
        self.assertIn("当前阶段", blocked.json()["detail"]["reasons"][0])
        self.assertEqual(escalation.status_code, 200)
        self.assertEqual(escalation.json()["status"], "skipped")
        self.assertEqual(briefing.status_code, 200)
        self.assertEqual(briefing.json()["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
