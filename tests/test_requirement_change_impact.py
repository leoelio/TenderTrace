from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.requirement_change_impact import requirement_change_impact


class RequirementChangeImpactTests(unittest.TestCase):
    def test_deadline_change_only_flags_deadline_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            deadline = _requirement(settings, "DEADLINE-01", "deadline")
            qualification = _requirement(settings, "QUAL-01", "qualification")
            _revision(settings, ["bid_deadline"])

            impact = requirement_change_impact(settings, "notice-1")

        self.assertTrue(impact["review_required"])
        self.assertEqual(impact["affected_count"], 1)
        self.assertEqual(impact["items"][0]["id"], deadline.id)
        self.assertEqual(impact["items"][0]["review_status"], "review")
        self.assertEqual(impact["items"][0]["status"], "pending")
        self.assertNotEqual(impact["items"][0]["id"], qualification.id)

    def test_attachment_change_flags_every_evidence_backed_requirement_without_overwriting_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            first = _requirement(settings, "QUAL-01", "qualification", status="confirmed")
            second = _requirement(settings, "SCORE-01", "scoring")
            _revision(settings, ["attachments"])

            impact = requirement_change_impact(settings, "notice-1")

        self.assertEqual(impact["affected_count"], 2)
        self.assertEqual({item["id"] for item in impact["items"]}, {first.id, second.id})
        first_impact = next(item for item in impact["items"] if item["id"] == first.id)
        self.assertEqual(first_impact["review_status_label"], "待复核")
        self.assertEqual(first_impact["status"], "confirmed")
        self.assertEqual(first.status, "confirmed")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text("TENDERTRACE_DB_PATH=data/test.sqlite3\n", encoding="utf-8")
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


def _requirement(settings: Settings, key: str, requirement_type: str, *, status: str = "pending"):
    return upsert_requirement(
        settings,
        notice_id="notice-1",
        requirement_key=key,
        requirement_type=requirement_type,
        title=f"{key} 要求",
        evidence_text="招标文件中的可复核原文。",
        source_url="https://example.com/notice-1",
        source_locator="公告正文片段",
        status=status,
    )


def _revision(settings: Settings, changed_fields: list[str]) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notice_revisions(id, notice_id, change_hash, changed_fields_json, before_json, after_json)
            VALUES (?, 'notice-1', ?, ?, '{}', '{}')
            """,
            (str(uuid4()), str(uuid4()), json_dumps(changed_fields)),
        )


if __name__ == "__main__":
    unittest.main()
