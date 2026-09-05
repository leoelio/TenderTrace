from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.delivery.feishu_bitable import FeishuBitableResult
from tendertrace.integrations.feishu import FeishuError
from tendertrace.integrations.feishu_requirement_sync import (
    sync_requirements_to_bitable,
    sync_requirements_to_feishu,
)
from tendertrace.opportunity_requirements import list_requirements, upsert_requirement


class _FakeFeishuClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.created: list[dict[str, str]] = []
        self.fail = fail

    def create_task(
        self,
        *,
        summary: str,
        description: str,
        client_token: str,
        due_timestamp_ms: str = "",
        assignee_open_id: str = "",
    ) -> dict[str, object]:
        if self.fail:
            raise FeishuError("simulated create_task failure")
        guid = f"task-{len(self.created) + 1}"
        self.created.append(
            {
                "summary": summary,
                "client_token": client_token,
                "assignee_open_id": assignee_open_id,
            }
        )
        return {"data": {"task": {"guid": guid}}}


class FeishuRequirementSyncTests(unittest.TestCase):
    def test_creates_tasks_idempotently_only_for_actionable_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            _requirement(settings, "QUAL-01", mandatory=True, status="pending")
            _requirement(settings, "SCORE-01", mandatory=False, status="completed")
            client = _FakeFeishuClient()

            first = sync_requirements_to_feishu(settings, "notice-1", client=client)
            second = sync_requirements_to_feishu(settings, "notice-1", client=client)

        self.assertEqual(first.status, "finished")
        self.assertEqual(first.scanned_count, 2)
        self.assertEqual(first.created_count, 1)
        self.assertEqual(first.skipped_count, 1)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.skipped_count, 2)
        self.assertIn("营业执照有效", client.created[0]["summary"])

    def test_records_task_guid_and_never_rewrites_requirement_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            requirement = _requirement(settings, "QUAL-01", mandatory=True, status="confirmed")
            client = _FakeFeishuClient()

            sync_requirements_to_feishu(settings, "notice-1", client=client)
            refreshed = list_requirements(settings, "notice-1")[0]
            with connection(settings) as conn:
                guid = conn.execute(
                    "SELECT feishu_task_guid FROM opportunity_requirements WHERE id = ?",
                    (requirement.id,),
                ).fetchone()[0]

        self.assertEqual(guid, "task-1")
        self.assertEqual(refreshed.status, "confirmed")
        self.assertEqual(refreshed.title, requirement.title)

    def test_sync_requirements_to_bitable_delegates_with_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            _requirement(settings, "QUAL-01", mandatory=True, status="pending")
            captured: dict[str, object] = {}

            def fake_writer(settings, *, notice_id, summary, requirements):
                captured["notice_id"] = notice_id
                captured["summary"] = summary
                captured["requirements"] = requirements
                return FeishuBitableResult(status="sent", updated_count=1)

            result = sync_requirements_to_bitable(
                settings, "notice-1", bitable_writer=fake_writer
            )

        self.assertEqual(result["status"], "sent")
        self.assertEqual(captured["notice_id"], "notice-1")
        self.assertEqual(captured["summary"]["total_count"], 1)
        self.assertEqual(len(captured["requirements"]), 1)

    def test_create_task_failure_is_recorded_without_blocking_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            _requirement(settings, "QUAL-01", mandatory=True, status="pending")
            client = _FakeFeishuClient(fail=True)

            result = sync_requirements_to_feishu(settings, "notice-1", client=client)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failed_count, 1)
        self.assertEqual(result.created_count, 0)
        self.assertEqual(len(result.failures), 1)
        self.assertIn("requirement_id", result.failures[0])


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
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


def _requirement(settings: Settings, key: str, *, mandatory: bool, status: str):
    return upsert_requirement(
        settings,
        notice_id="notice-1",
        requirement_key=key,
        requirement_type="qualification",
        title="营业执照有效" if key == "QUAL-01" else "评分办法",
        evidence_text="投标人须具有有效的营业执照。" if key == "QUAL-01" else "技术方案满分30分。",
        source_url="https://example.com/notice-1",
        source_locator="招标文件第 3 页",
        mandatory=mandatory,
        status=status,
        actor="测试",
    )


if __name__ == "__main__":
    unittest.main()
