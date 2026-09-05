from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.llm.gateway import ModelCallResult
from tendertrace.pipeline.summarize import summarize_notice_with_model


class _FakeGateway:
    def __init__(self, summary: str | None, status: str = "ok") -> None:
        self.summary = summary
        self.status = status

    def generate_json(self, *, system: str, user: str) -> ModelCallResult:
        return ModelCallResult(
            mode="local",
            provider="ollama",
            model="test-model",
            status=self.status,
            parsed={"summary": self.summary, "key_facts": []} if self.summary is not None else None,
        )


class SummarizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.title = "某服务器采购项目招标公告"
        self.content = "本项目预算100万元，投标截止2026年9月16日，项目编号ZB2024-001。"
        self.core = "预算100万元，截止2026年9月16日。"

    def test_model_summary_passes_when_all_digits_are_grounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            result = summarize_notice_with_model(
                settings,
                title=self.title,
                content_text=self.content,
                core_content=self.core,
                gateway=_FakeGateway("本项目预算100万元，投标截止2026年9月16日。"),
            )

        self.assertEqual(result.source, "model")
        self.assertTrue(result.fact_check_passed)
        self.assertEqual(result.missing_digits, ())
        self.assertIn("100", result.checked_digits)

    def test_model_summary_falls_back_when_a_digit_is_hallucinated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            result = summarize_notice_with_model(
                settings,
                title=self.title,
                content_text=self.content,
                core_content=self.core,
                gateway=_FakeGateway("本项目预算200万元，投标截止2026年9月16日。"),
            )

        self.assertEqual(result.source, "extractive")
        self.assertFalse(result.fact_check_passed)
        self.assertIn("200", result.missing_digits)
        self.assertIn("100", result.summary)

    def test_empty_model_summary_falls_back_to_extractive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            result = summarize_notice_with_model(
                settings,
                title=self.title,
                content_text=self.content,
                core_content=self.core,
                gateway=_FakeGateway(""),
            )

        self.assertEqual(result.source, "extractive")
        self.assertTrue(result.fact_check_passed)

    def test_disabled_model_returns_extractive_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            result = summarize_notice_with_model(
                settings,
                title=self.title,
                content_text=self.content,
                core_content=self.core,
            )

        self.assertEqual(result.source, "extractive")
        self.assertEqual(result.model_status, "skipped")

    def test_extractive_summary_uses_core_content_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            result = summarize_notice_with_model(
                settings,
                title=self.title,
                content_text="",
                core_content="",
                gateway=_FakeGateway(None),
            )

        self.assertEqual(result.summary, "详情页正文暂未抽取到可用内容。")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


if __name__ == "__main__":
    unittest.main()
