from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.organization_memory import create_workspace
from tendertrace.opportunity_collaboration import (
    list_collaboration_notes,
    record_collaboration_note,
)


class OpportunityCollaborationTests(unittest.TestCase):
    def test_note_is_scoped_to_opportunity_deduplicated_by_feishu_message_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            first = record_collaboration_note(
                settings,
                notice_id="notice-1",
                content=" 请售前确认交付边界。 ",
                actor="ou_sales",
                channel="feishu_group",
                source_message_id="om-1",
            )
            duplicate = record_collaboration_note(
                settings,
                notice_id="notice-1",
                content="重复回调不应重复记录",
                actor="ou_sales",
                channel="feishu_group",
                source_message_id="om-1",
            )
            notes = list_collaboration_notes(settings, "notice-1")
            with connection(settings) as conn:
                event = conn.execute(
                    "SELECT action FROM opportunity_events WHERE notice_id = ?",
                    ("notice-1",),
                ).fetchone()

        self.assertEqual(first.id, duplicate.id)
        self.assertEqual(notes[0].content, "请售前确认交付边界。")
        self.assertEqual(len(notes), 1)
        self.assertEqual(event["action"], "collaboration_note_recorded")

    def test_note_rejects_unknown_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            with self.assertRaisesRegex(ValueError, "unsupported"):
                record_collaboration_note(
                    settings,
                    notice_id="notice-1",
                    content="test",
                    actor="admin",
                    channel="email",
                )

    def test_api_returns_notes_and_launches_war_room_through_audited_service(self) -> None:
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            workspace = create_workspace(
                settings,
                name="机会战情室",
                feishu_chat_id="oc_workspace_team",
            )
            with patch.object(api_module.Settings, "load", return_value=settings), patch.object(
                api_module,
                "launch_war_room",
                return_value={
                    "status": "started",
                    "notice_id": "notice-1",
                    "message": "飞书战情室已启动",
                    "completed_count": 4,
                    "failed_count": 0,
                    "steps": [],
                },
            ) as launcher:
                client = TestClient(api_module.create_app())
                saved = client.post(
                    "/api/opportunities/notice-1/collaboration-notes",
                    json={"content": "确认售前支持范围", "actor": "销售经理"},
                )
                listed = client.get("/api/opportunities/notice-1/collaboration-notes")
                launched = client.post(
                    "/api/opportunities/notice-1/war-room/launch",
                    json={"workspace_id": workspace.id},
                )
                planned = client.get(
                    "/api/opportunities/notice-1/war-room",
                    params={"workspace_id": workspace.id},
                )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(listed.json()["returned"], 1)
        self.assertEqual(launched.status_code, 200)
        self.assertEqual(planned.status_code, 200)
        self.assertEqual(planned.json()["steps"][0]["status"], "ready")
        self.assertIn("当前项目群", planned.json()["steps"][0]["detail"])
        launcher.assert_called_once()
        self.assertEqual(launcher.call_args.kwargs["receive_id"], "oc_workspace_team")
        self.assertEqual(launcher.call_args.kwargs["receive_id_type"], "chat_id")
        self.assertEqual(launched.json()["status"], "started")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n"
        "TENDERTRACE_SCHEDULER_ENABLED=false\n"
        "FEISHU_APP_ID=cli_test\n"
        "FEISHU_APP_SECRET=secret-value\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES ('notice-1', 'ccgp', 'https://example.com/notice-1',
                    'https://example.com/notice-1', '服务器采购项目')
            """
        )


if __name__ == "__main__":
    unittest.main()
