from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
import warnings

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_requirements import (
    list_requirements,
    requirement_summary,
    upsert_requirement,
)


class OpportunityRequirementTests(unittest.TestCase):
    def test_requirement_is_evidence_backed_idempotent_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            first = upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key="QUAL-01",
                requirement_type="qualification",
                title="营业执照有效",
                evidence_text="投标人须具有有效的营业执照。",
                source_url="https://example.com/notice-1",
                source_locator="招标文件第 3 页，第 2.1 条",
                mandatory=True,
                confidence=92,
                actor="分析师",
            )
            second = upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key="QUAL-01",
                requirement_type="qualification",
                title="营业执照有效",
                evidence_text="投标人须具有有效的营业执照。",
                source_url="https://example.com/notice-1",
                source_locator="招标文件第 3 页，第 2.1 条",
                mandatory=True,
                confidence=100,
                status="confirmed",
                actor="法务",
            )
            requirements = list_requirements(settings, "notice-1")
            summary = requirement_summary(settings, "notice-1")
            with connection(settings) as conn:
                event_count = conn.execute(
                    "SELECT COUNT(*) FROM opportunity_events "
                    "WHERE notice_id = ? AND action = 'requirement_upserted'",
                    ("notice-1",),
                ).fetchone()[0]

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(requirements), 1)
        self.assertEqual(requirements[0].status, "confirmed")
        self.assertEqual(requirements[0].confidence, 100)
        self.assertTrue(requirements[0].mandatory)
        self.assertEqual(summary["total_count"], 1)
        self.assertEqual(summary["confirmed_count"], 1)
        self.assertEqual(summary["mandatory_pending_count"], 0)
        self.assertEqual(event_count, 2)

    def test_requirement_rejects_missing_evidence_and_invalid_assignee(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            with self.assertRaisesRegex(ValueError, "evidence_text"):
                upsert_requirement(
                    settings,
                    notice_id="notice-1",
                    requirement_key="DEADLINE-01",
                    requirement_type="deadline",
                    title="投标截止时间",
                    evidence_text="",
                    source_url="https://example.com/notice-1",
                    source_locator="公告第 1 页",
                )
            with self.assertRaisesRegex(ValueError, "assignee_member_id"):
                upsert_requirement(
                    settings,
                    notice_id="notice-1",
                    requirement_key="DEADLINE-01",
                    requirement_type="deadline",
                    title="投标截止时间",
                    evidence_text="投标截止时间为 2026-09-16 09:00。",
                    source_url="https://example.com/notice-1",
                    source_locator="公告第 1 页",
                    assignee_member_id="missing-member",
                )

    def test_requirement_api_saves_and_lists_evidence_backed_rows(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_db_path = os.environ.get("TENDERTRACE_DB_PATH")
            old_scheduler = os.environ.get("TENDERTRACE_SCHEDULER_ENABLED")
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "api.sqlite3")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                settings = Settings.load()
                init_db(settings)
                _insert_notice(settings)
                client = TestClient(create_app())
                saved = client.post(
                    "/api/opportunities/notice-1/requirements",
                    json={
                        "requirement_key": "ATTACH-01",
                        "requirement_type": "attachment",
                        "title": "法人授权书",
                        "evidence_text": "授权委托书须加盖公章。",
                        "source_url": "https://example.com/notice-1",
                        "source_locator": "附件 4，第 1 页",
                        "mandatory": True,
                        "confidence": 88,
                    },
                )
                listed = client.get("/api/opportunities/notice-1/requirements")
            finally:
                if old_db_path is None:
                    os.environ.pop("TENDERTRACE_DB_PATH", None)
                else:
                    os.environ["TENDERTRACE_DB_PATH"] = old_db_path
                if old_scheduler is None:
                    os.environ.pop("TENDERTRACE_SCHEDULER_ENABLED", None)
                else:
                    os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = old_scheduler

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["requirement"]["requirement_key"], "ATTACH-01")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["summary"]["mandatory_pending_count"], 1)
        self.assertEqual(len(listed.json()["items"]), 1)


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
