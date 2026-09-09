from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from tendertrace.app import api as api_module
from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.integrations.feishu_review_board import ReviewBoardDeliveryResult
from tendertrace.opportunity_requirements import list_requirements, upsert_requirement
from tendertrace.requirement_review_board import (
    list_requirement_review_cases,
    resolve_requirement_review_case,
    sync_requirement_review_cases,
)


class RequirementReviewBoardTests(unittest.TestCase):
    def test_sync_routes_cases_and_human_resolution_preserves_requirement_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            requirement = upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key="DEADLINE-01",
                requirement_type="deadline",
                title="投标截止时间",
                evidence_text="投标截止时间为 2026-09-16 09:00。",
                source_url="https://example.com/notice-1",
                source_locator="公告第 1 页",
                mandatory=True,
                confidence=55,
                status="confirmed",
            )
            _revision(settings, ["bid_deadline"])

            first = sync_requirement_review_cases(settings, "notice-1")
            second = sync_requirement_review_cases(settings, "notice-1")
            cases = list_requirement_review_cases(settings, "notice-1")
            resolved = resolve_requirement_review_case(
                settings,
                "notice-1",
                cases[0].id,
                decision="returned",
                actor="法务",
                note="请依据最新截止时间更新倒排计划。",
            )
            refreshed = list_requirements(settings, "notice-1")
            with connection(settings) as conn:
                actions = [
                    str(row["action"])
                    for row in conn.execute(
                        "SELECT action FROM opportunity_events WHERE notice_id = ? ORDER BY rowid",
                        ("notice-1",),
                    ).fetchall()
                ]

        self.assertEqual(first["created_count"], 2)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual({item.reviewer_role for item in cases}, {"project_control", "evidence_audit"})
        self.assertEqual(resolved.status, "resolved")
        self.assertEqual(refreshed[0].id, requirement.id)
        self.assertEqual(refreshed[0].status, "confirmed")
        self.assertIn("requirement_review_created", actions)
        self.assertIn("requirement_review_resolved", actions)

    def test_second_notice_revision_creates_a_new_evidence_review_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key="QUAL-01",
                requirement_type="qualification",
                title="资质要求",
                evidence_text="投标人须提供有效资质。",
                source_url="https://example.com/notice-1",
                source_locator="公告第 1 页",
                confidence=90,
                status="confirmed",
            )
            first_revision = _revision(settings, ["attachments"])
            first = sync_requirement_review_cases(settings, "notice-1")
            first_case = next(
                item
                for item in list_requirement_review_cases(settings, "notice-1")
                if item.reason == f"notice_change_impact:{first_revision}"
            )
            resolve_requirement_review_case(
                settings,
                "notice-1",
                first_case.id,
                decision="accepted",
                actor="证据审计",
                note="已依据第一版附件复核。",
            )
            second_revision = _revision(settings, ["attachments"])
            second = sync_requirement_review_cases(settings, "notice-1")
            cases = list_requirement_review_cases(settings, "notice-1")
            second_case = next(
                item
                for item in cases
                if item.reason == f"notice_change_impact:{second_revision}"
            )

        self.assertGreater(first["created_count"], 0)
        self.assertEqual(second["created_count"], 1)
        self.assertNotEqual(first_case.id, second_case.id)
        self.assertEqual(second_case.status, "pending")
        self.assertEqual(second_case.reason_label, "公告证据发生变化，需重新核验。")

    def test_review_board_api_syncs_then_resolves_a_case(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key="QUAL-01",
                requirement_type="qualification",
                title="营业执照有效",
                evidence_text="投标人须具有有效的营业执照。",
                source_url="https://example.com/notice-1",
                source_locator="招标文件第 3 页",
                mandatory=True,
                confidence=60,
            )
            with patch.object(api_module.Settings, "load", return_value=settings):
                client = TestClient(api_module.create_app())
                synced = client.post("/api/opportunities/notice-1/review-board/sync")
                review_id = synced.json()["items"][0]["id"]
                resolved = client.post(
                    f"/api/opportunities/notice-1/review-board/{review_id}/resolve",
                    json={"decision": "accepted", "actor": "销售经理", "note": "资料已核验。"},
                )
                listed = client.get("/api/opportunities/notice-1/review-board")

        self.assertEqual(synced.status_code, 200)
        self.assertGreater(synced.json()["created_count"], 0)
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(listed.json()["summary"]["resolved_count"], 1)

    def test_review_board_api_can_deliver_the_current_board_to_feishu(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            result = ReviewBoardDeliveryResult(
                status="sent",
                notice_id="notice-1",
                pending_count=2,
                suggestion_count=1,
                artifact_key="review-key",
                message_id="om_review",
            )
            with patch.object(api_module.Settings, "load", return_value=settings), patch.object(
                api_module,
                "send_requirement_review_digest",
                return_value=result,
            ) as sender:
                client = TestClient(api_module.create_app())
                response = client.post("/api/opportunities/notice-1/review-board/send-feishu")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message_id"], "om_review")
        sender.assert_called_once_with(
            settings,
            "notice-1",
            receive_id=None,
            receive_id_type=None,
            force=False,
        )


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


def _revision(settings: Settings, changed_fields: list[str]) -> str:
    revision_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notice_revisions(id, notice_id, change_hash, changed_fields_json, before_json, after_json)
            VALUES (?, 'notice-1', ?, ?, '{}', '{}')
            """,
            (revision_id, str(uuid4()), json_dumps(changed_fields)),
        )
    return revision_id


if __name__ == "__main__":
    unittest.main()
