from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_team import (
    remove_team_member,
    team_snapshots,
    team_summary,
    upsert_team_member,
)
from tendertrace.integrations.feishu_team import sync_opportunity_team
from tendertrace.workflow import update_workflow


class OpportunityTeamTests(unittest.TestCase):
    def test_member_upsert_is_idempotent_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            first = upsert_team_member(
                settings,
                notice_id="notice-1",
                member_open_id="ou_solution",
                member_name="李工",
                role="solution",
                responsibility="确认技术边界",
                actor="ou_owner",
            )
            second = upsert_team_member(
                settings,
                notice_id="notice-1",
                member_open_id="ou_solution",
                member_name="李工",
                role="solution",
                responsibility="复核技术方案",
                actor="ou_owner",
            )
            with connection(settings) as conn:
                member_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_team_members"
                ).fetchone()[0]
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_events "
                    "WHERE action = 'team_member_upserted'"
                ).fetchone()[0]

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.responsibility, "复核技术方案")
        self.assertEqual(member_count, 1)
        self.assertEqual(event_count, 2)

    def test_partner_member_requires_organization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            with self.assertRaisesRegex(ValueError, "organization_name"):
                upsert_team_member(
                    settings,
                    notice_id="notice-1",
                    member_name="合作伙伴",
                    role="partner_lead",
                    organization_type="partner",
                )

    def test_stage_changes_required_role_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            workflow = update_workflow(
                settings,
                "notice-1",
                owner_open_id="ou_owner",
                owner_name="张三",
            )
            pursuing = replace(workflow, stage="pursuing", stage_label="策略制定")
            initial = team_summary(pursuing, [])

            upsert_team_member(
                settings,
                notice_id="notice-1",
                member_name="李工",
                role="solution",
            )
            after_solution = team_snapshots(
                settings,
                {"notice-1": pursuing},
            )["notice-1"]
            removed = remove_team_member(
                settings,
                notice_id="notice-1",
                member_id=str(after_solution["members"][0]["id"]),
            )
            after_removal = team_snapshots(
                settings,
                {"notice-1": pursuing},
            )["notice-1"]

        self.assertEqual(initial["coverage_score"], 33)
        self.assertEqual(initial["missing_roles"], ["方案技术", "商务报价"])
        self.assertEqual(after_solution["coverage_score"], 67)
        self.assertEqual(after_solution["missing_roles"], ["商务报价"])
        self.assertEqual(removed.status, "removed")
        self.assertEqual(after_removal["member_count"], 0)

    def test_task_sync_adds_and_removes_members_as_followers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            update_workflow(settings, "notice-1", feishu_task_guid="task-guid")
            member = upsert_team_member(
                settings,
                notice_id="notice-1",
                member_open_id="ou_solution",
                member_name="李工",
                role="solution",
            )
            client = _FakeTeamClient()

            added = sync_opportunity_team(settings, "notice-1", client=client)
            remove_team_member(
                settings,
                notice_id="notice-1",
                member_id=member.id,
            )
            removed = sync_opportunity_team(settings, "notice-1", client=client)

        self.assertEqual(added.added_count, 1)
        self.assertEqual(removed.removed_count, 1)
        self.assertEqual(
            client.calls,
            [
                ("add", "task-guid", ["ou_solution"], "follower"),
                ("remove", "task-guid", ["ou_solution"], "follower"),
            ],
        )


class _FakeTeamClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[str], str]] = []

    def add_task_members(
        self,
        task_guid: str,
        *,
        assignee_open_ids: list[str],
        role: str,
    ) -> dict[str, object]:
        self.calls.append(("add", task_guid, assignee_open_ids, role))
        return {"code": 0}

    def remove_task_members(
        self,
        task_guid: str,
        *,
        member_open_ids: list[str],
        role: str,
    ) -> dict[str, object]:
        self.calls.append(("remove", task_guid, member_open_ids, role))
        return {"code": 0}


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n",
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
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "notice-1",
                "ccgp",
                "https://example.com/notice-1",
                "https://example.com/notice-1",
                "服务器采购项目",
            ),
        )


if __name__ == "__main__":
    unittest.main()
