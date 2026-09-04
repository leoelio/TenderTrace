from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.requirement_extraction import extract_and_save_requirements
from tendertrace.opportunity_requirements import list_requirements, upsert_requirement


class RequirementExtractionTests(unittest.TestCase):
    def test_rules_extract_five_requirement_types_with_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)

            result = extract_and_save_requirements(settings, "notice-1")
            requirements = list_requirements(settings, "notice-1")

        types = {item.requirement_type for item in requirements}
        self.assertEqual(result["status"], "finished")
        self.assertTrue({"qualification", "deadline", "scoring", "disqualification", "attachment"} <= types)
        self.assertTrue(all(item.evidence_text and item.source_locator for item in requirements))
        self.assertTrue(any(item.source_locator.startswith("附件：招标文件") for item in requirements))

    def test_rules_do_not_overwrite_human_confirmed_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            seeded = extract_and_save_requirements(settings, "notice-1")
            requirement = list_requirements(settings, "notice-1")[0]
            upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key=requirement.requirement_key,
                requirement_type=requirement.requirement_type,
                title="人工确认后的要求",
                evidence_text="人工复核后的原文摘录。",
                source_url=requirement.source_url,
                source_locator=requirement.source_locator,
                status="confirmed",
                actor="人工复核",
            )

            extracted = extract_and_save_requirements(settings, "notice-1")
            refreshed = {item.requirement_key: item for item in list_requirements(settings, "notice-1")}

        self.assertGreater(seeded["created_or_updated_count"], 0)
        self.assertGreater(extracted["preserved_count"], 0)
        self.assertEqual(refreshed[requirement.requirement_key].title, "人工确认后的要求")
        self.assertEqual(refreshed[requirement.requirement_key].status, "confirmed")

    def test_extraction_api_returns_a_pending_review_summary(self) -> None:
        from fastapi.testclient import TestClient
        from tendertrace.app import api as api_module

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            with patch.object(api_module.Settings, "load", return_value=settings):
                response = TestClient(api_module.create_app()).post(
                    "/api/opportunities/notice-1/requirements/extract"
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "finished")
        self.assertGreater(response.json()["summary"]["mandatory_pending_count"], 0)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    attachment_text = (
        "评分办法：技术方案满分 30 分，商务部分满分 20 分。"
        "投标人不得提供虚假材料，否则按无效投标处理。"
        "投标文件须提供营业执照复印件和法人授权书。"
    )
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, content_text, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "notice-1",
                "ccgp",
                "https://example.com/notice-1",
                "https://example.com/notice-1",
                "服务器采购项目",
                "投标人须具有有效的营业执照。投标文件递交截止时间：2026年9月16日09时00分。",
                json_dumps(
                    {
                        "attachment_snapshots": [
                            {
                                "name": "招标文件.pdf",
                                "url": "https://example.com/tender.pdf",
                                "status": "extracted",
                                "text_excerpt": attachment_text,
                            }
                        ]
                    }
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
