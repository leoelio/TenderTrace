from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.opportunity_team import upsert_team_member
from tendertrace.requirement_review_actions import (
    bind_review_action_to_requirement,
    complete_review_action,
    create_review_action,
    list_review_actions,
    review_action_summary,
)
from tendertrace.requirement_review_human_opinions import record_human_review_opinion


class RequirementReviewActionTests(unittest.TestCase):
    def test_opinion_converts_once_to_auditable_action_then_completes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            requirement = _requirement(settings)
            member = upsert_team_member(
                settings,
                notice_id="notice-1",
                member_name="方案负责人",
                member_open_id="ou_solution",
                role="solution",
                responsibility="补充技术规格材料",
            )
            opinion = record_human_review_opinion(
                settings,
                notice_id="notice-1",
                requirement_id=requirement.id,
                content="需补充服务器配置的原厂规格书。",
                actor="项目经理",
                channel="feishu_group",
                source_message_id="msg-1",
            )
            first = create_review_action(
                settings,
                notice_id="notice-1",
                opinion_id=opinion.id,
                assignee_member_id=member.id,
                due_at="2026-09-10T10:00",
                action_note="向产品团队索取并核验原厂规格书。",
                actor="项目经理",
            )
            repeated = create_review_action(
                settings,
                notice_id="notice-1",
                opinion_id=opinion.id,
                assignee_member_id=member.id,
                due_at="2026-09-10T10:00",
                action_note="不应重复创建。",
                actor="项目经理",
            )
            bound = bind_review_action_to_requirement(
                settings,
                notice_id="notice-1",
                action_id=first.id,
            )
            completed = complete_review_action(
                settings,
                notice_id="notice-1",
                action_id=first.id,
                actor="方案负责人",
                completion_note="规格书已上传并完成型号核验。",
            )
            summary = review_action_summary(settings, "notice-1")
            actions = list_review_actions(settings, "notice-1")
            with connection(settings) as conn:
                requirement_row = conn.execute(
                    "SELECT assignee_member_id, due_at, status FROM opportunity_requirements WHERE id = ?",
                    (requirement.id,),
                ).fetchone()
                events = [
                    row["action"]
                    for row in conn.execute(
                        "SELECT action FROM opportunity_events WHERE notice_id = ? ORDER BY rowid",
                        ("notice-1",),
                    ).fetchall()
                ]

        self.assertEqual(first.id, repeated.id)
        self.assertEqual(first.action_note, "向产品团队索取并核验原厂规格书。")
        self.assertEqual(bound.assignee_member_id, member.id)
        self.assertEqual(requirement_row["assignee_member_id"], member.id)
        self.assertEqual(requirement_row["due_at"], "2026-09-10T10:00")
        self.assertEqual(requirement_row["status"], "assigned")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.completion_note, "规格书已上传并完成型号核验。")
        self.assertEqual(len(actions), 1)
        self.assertEqual(summary["completed_count"], 1)
        self.assertIn("requirement_review_action_created", events)
        self.assertIn("requirement_review_action_bound_to_requirement_task", events)
        self.assertIn("requirement_review_action_completed", events)

    def test_action_allows_missing_owner_and_due_date_without_inventing_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            requirement = _requirement(settings)
            opinion = record_human_review_opinion(
                settings,
                notice_id="notice-1",
                requirement_id=requirement.id,
                content="需要确认报价口径。",
                actor="商务",
                channel="web",
            )
            action = create_review_action(
                settings,
                notice_id="notice-1",
                opinion_id=opinion.id,
                assignee_member_id="",
                due_at="",
                action_note="等待负责人确认后再同步任务。",
                actor="商务",
            )
            summary = review_action_summary(settings, "notice-1")

        self.assertEqual(action.assignee_member_id, "")
        self.assertEqual(action.due_at, "")
        self.assertEqual(summary["unassigned_count"], 1)
        self.assertEqual(summary["undated_count"], 1)

    def test_review_action_api_is_available_from_review_board(self) -> None:
        from unittest.mock import patch

        from fastapi.testclient import TestClient
        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            requirement = _requirement(settings)
            opinion = record_human_review_opinion(
                settings,
                notice_id="notice-1",
                requirement_id=requirement.id,
                content="补充资质附件。",
                actor="法务",
                channel="web",
            )
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                created = client.post(
                    f"/api/opportunities/notice-1/review-board/opinions/{opinion.id}/actions",
                    json={"action_note": "准备并上传资质附件。", "actor": "法务"},
                )
                action_id = created.json()["action"]["id"]
                completed = client.post(
                    f"/api/opportunities/notice-1/review-board/actions/{action_id}/complete",
                    json={"actor": "法务", "completion_note": "附件已上传。"},
                )
                board = client.get("/api/opportunities/notice-1/review-board")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(board.json()["action_summary"]["completed_count"], 1)
        self.assertEqual(board.json()["actions"][0]["completion_note"], "附件已上传。")

    def test_sync_api_binds_only_the_confirmed_requirement_before_feishu_call(self) -> None:
        from unittest.mock import patch

        from fastapi.testclient import TestClient
        from tendertrace.app import api as api_module
        from tendertrace.integrations.feishu_requirement_sync import RequirementSyncResult

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            requirement = _requirement(settings)
            member = upsert_team_member(
                settings,
                notice_id="notice-1",
                member_name="方案负责人",
                member_open_id="ou_solution",
                role="solution",
            )
            opinion = record_human_review_opinion(
                settings,
                notice_id="notice-1",
                requirement_id=requirement.id,
                content="补充规格书。",
                actor="项目经理",
                channel="web",
            )
            action = create_review_action(
                settings,
                notice_id="notice-1",
                opinion_id=opinion.id,
                assignee_member_id=member.id,
                due_at="2026-09-10T10:00",
                action_note="补充并核验规格书。",
                actor="项目经理",
            )
            result = RequirementSyncResult("finished", 1, 1, 0, 0)
            with patch.object(api_module.Settings, "load", return_value=settings), patch.object(
                api_module, "sync_requirements_to_feishu", return_value=result
            ) as syncer:
                client = TestClient(api_module.create_app())
                response = client.post(
                    f"/api/opportunities/notice-1/review-board/actions/{action.id}/sync-feishu"
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sync"]["created_count"], 1)
        self.assertEqual(syncer.call_args.kwargs["requirement_ids"], {requirement.id})


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text("TENDERTRACE_DB_PATH=data/test.sqlite3\n", encoding="utf-8")
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _requirement(settings: Settings):
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES ('notice-1', 'ccgp', 'https://example.com/notice-1',
                    'https://example.com/notice-1', '服务器采购项目')
            """
        )
    return upsert_requirement(
        settings,
        notice_id="notice-1",
        requirement_key="TECH-01",
        requirement_type="qualification",
        title="服务器技术规格",
        evidence_text="投标产品须提供可核验规格。",
        source_url="https://example.com/notice-1",
        source_locator="公告第 2 页",
    )


if __name__ == "__main__":
    unittest.main()
