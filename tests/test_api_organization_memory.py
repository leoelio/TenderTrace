from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


class FakeFeishuClient:
    created: list[dict[str, object]] = []
    invited: list[tuple[str, list[str]]] = []

    def __init__(self, settings) -> None:
        self.settings = settings

    def create_chat(self, **kwargs):
        self.created.append(kwargs)
        return {"chat_id": "oc_api_team"}

    def add_chat_members(self, chat_id: str, member_open_ids: list[str]):
        self.invited.append((chat_id, member_open_ids))
        return {"invalid_id_list": []}


class OrganizationMemoryApiTests(unittest.TestCase):
    def test_group_workspace_memory_search_invite_and_fact_conversion(self) -> None:
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = _environment(root)
            previous = {key: os.environ.get(key) for key in values}
            os.environ.update(values)
            FakeFeishuClient.created.clear()
            FakeFeishuClient.invited.clear()
            try:
                settings = Settings.load()
                init_db(settings)
                _insert_notice(settings)
                with patch.object(api_module, "FeishuClient", FakeFeishuClient):
                    with TestClient(api_module.create_app()) as client:
                        created = client.post(
                            "/api/organization/workspaces",
                            json={
                                "name": "服务器机会战队",
                                "members": [
                                    {"open_id": "ou_owner", "name": "负责人", "role": "owner"}
                                ],
                            },
                        )
                        workspace_id = created.json()["workspace"]["id"]
                        invited = client.post(
                            f"/api/organization/workspaces/{workspace_id}/members",
                            json={"members": [{"open_id": "ou_partner", "role": "partner"}]},
                        )
                        recorded = client.post(
                            f"/api/organization/workspaces/{workspace_id}/memories",
                            json={
                                "memory_type": "customer_signal",
                                "title": "预算经确认",
                                "content": "客户会议确认预算为 500 万元。",
                                "related_notice_id": "notice-org",
                                "evidence_url": "https://example.com/minutes",
                            },
                        )
                        memory_id = recorded.json()["memory"]["id"]
                        searched = client.get(
                            f"/api/organization/workspaces/{workspace_id}/memories",
                            params={"query": "预算确认"},
                        )
                        converted = client.post(
                            f"/api/organization/workspaces/{workspace_id}/memories/{memory_id}/convert",
                            json={
                                "target_type": "opportunity_fact",
                                "notice_id": "notice-org",
                                "facts": {"budget": "5000000"},
                            },
                        )
                        action_converted = client.post(
                            f"/api/organization/workspaces/{workspace_id}/memories/{memory_id}/convert",
                            json={
                                "target_type": "relationship_action",
                                "notice_id": "notice-org",
                                "title": "与客户确认预算审批口径",
                                "due_at": "2026-08-20T09:00",
                                "priority": "high",
                            },
                        )
                        listed = client.get("/api/organization/workspaces")
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(created.status_code, 200)
        self.assertEqual(invited.status_code, 200)
        self.assertEqual(recorded.status_code, 200)
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(len(searched.json()["items"]), 1)
        self.assertEqual(converted.status_code, 200)
        self.assertEqual(converted.json()["target_type"], "opportunity_fact")
        self.assertEqual(action_converted.status_code, 200)
        self.assertEqual(action_converted.json()["result"]["source_type"], "organization_memory")
        self.assertEqual(listed.json()["items"][0]["member_count"], 2)
        self.assertEqual(FakeFeishuClient.invited, [("oc_api_team", ["ou_partner"])])


def _environment(root: Path) -> dict[str, str]:
    return {
        "TENDERTRACE_DB_PATH": str(root / "data" / "db.sqlite3"),
        "TENDERTRACE_OUTPUTS_DIR": str(root / "outputs"),
        "TENDERTRACE_OUTBOX_DIR": str(root / "outbox"),
        "TENDERTRACE_SNAPSHOTS_DIR": str(root / "snapshots"),
        "TENDERTRACE_TRACES_DIR": str(root / "traces"),
        "TENDERTRACE_SECRETS_DIR": str(root / "secrets"),
        "TENDERTRACE_SCHEDULER_ENABLED": "false",
        "TENDERTRACE_MODEL_MODE": "local",
        "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED": "false",
        "FEISHU_ENABLED": "true",
        "FEISHU_APP_ID": "cli_test",
        "FEISHU_APP_SECRET": "secret-value",
    }


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, publish_time,
                purchaser, content_text, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "notice-org",
                "ccgp",
                "https://example.com/notice-org",
                "https://example.com/notice-org",
                "服务器采购项目",
                "2026-08-16",
                "示例采购人",
                "服务器采购项目",
                "{}",
            ),
        )


if __name__ == "__main__":
    unittest.main()
