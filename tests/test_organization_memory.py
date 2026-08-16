from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.organization_memory import (
    add_members,
    create_workspace,
    list_workspaces,
    record_memory,
    search_memories,
)


class OrganizationMemoryTests(unittest.TestCase):
    def test_workspace_memory_is_scoped_searchable_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            first = create_workspace(
                settings,
                name="华东服务器项目组",
                feishu_chat_id="oc_east",
                members=[{"open_id": "ou_owner", "name": "负责人", "role": "owner"}],
            )
            second = create_workspace(
                settings,
                name="西南项目组",
                feishu_chat_id="oc_west",
            )
            memory = record_memory(
                settings,
                workspace_id=first.id,
                memory_type="customer_signal",
                title="客户关注国产化适配",
                content="客户要求服务器支持国产操作系统与数据库兼容认证。",
                source_type="feishu_message",
                source_message_id="om_memory",
                sender_open_id="ou_owner",
                actor="ou_owner",
            )
            duplicate = record_memory(
                settings,
                workspace_id=first.id,
                content="客户要求服务器支持国产操作系统与数据库兼容认证。",
                title="客户关注国产化适配",
                memory_type="customer_signal",
                source_type="feishu_message",
                source_message_id="om_memory",
                sender_open_id="ou_owner",
                actor="ou_owner",
            )
            matching = search_memories(settings, workspace_id=first.id, query="国产数据库")
            isolated = search_memories(settings, workspace_id=second.id, query="国产数据库")
            workspaces = list_workspaces(settings)
            with connection(settings) as conn:
                event_count = conn.execute(
                    "SELECT COUNT(*) count FROM organization_memory_events WHERE workspace_id = ?",
                    (first.id,),
                ).fetchone()["count"]

        self.assertEqual(memory.id, duplicate.id)
        self.assertEqual([item.id for item in matching], [memory.id])
        self.assertEqual(isolated, [])
        self.assertEqual(next(item for item in workspaces if item.id == first.id).memory_count, 1)
        self.assertGreaterEqual(event_count, 2)

    def test_member_upsert_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            workspace = create_workspace(
                settings,
                name="投标协同",
                feishu_chat_id="oc_team",
            )
            members = add_members(
                settings,
                workspace.id,
                [{"open_id": "ou_partner", "name": "伙伴甲", "role": "partner"}],
            )

            with self.assertRaises(ValueError):
                record_memory(
                    settings,
                    workspace_id=workspace.id,
                    content="无效类型",
                    memory_type="unknown",
                )

        self.assertEqual(members[0]["role"], "partner")


if __name__ == "__main__":
    unittest.main()
