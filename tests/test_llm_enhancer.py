from pathlib import Path
import tempfile
import unittest
from typing import Any

from tendertrace.config import Settings
from tendertrace.llm.enhancer import enhance_bidql_with_model
from tendertrace.llm.gateway import ModelCallResult


class FakeGateway:
    def __init__(self, result: ModelCallResult) -> None:
        self.result = result
        self.calls: list[dict[str, str]] = []

    def generate_json(self, *, system: str, user: str) -> ModelCallResult:
        self.calls.append({"system": system, "user": user})
        return self.result


class ModelEnhancerTests(unittest.TestCase):
    def test_model_suggestions_are_applied_conservatively(self) -> None:
        bidql = _bidql()
        gateway = FakeGateway(
            ModelCallResult(
                mode="local",
                provider="ollama",
                model="qwen3:8b",
                status="ok",
                text="{}",
                parsed={
                    "expanded_keywords": [
                        "GPU服务器",
                        "服务器中标公告",
                        "服务器",
                        "https://bad.example",
                    ],
                    "negative_keywords": ["废标", "中标"],
                    "intent_summary": "server tender search",
                    "confidence": 0.88,
                },
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            enhancement = enhance_bidql_with_model(settings, bidql, gateway=gateway)

        topic = enhancement.bidql["topic"]
        self.assertEqual(topic["core"], ["服务器"])
        self.assertEqual(enhancement.applied_keywords, ["GPU服务器"])
        self.assertEqual(enhancement.applied_negatives, ["废标"])
        self.assertIn({"term": "GPU服务器", "weight": 0.72, "origin": "model"}, topic["expanded"])
        self.assertNotIn("服务器中标公告", [item.get("term") for item in topic["expanded"]])
        self.assertIn("model", enhancement.bidql["meta"]["channels"])
        self.assertEqual(
            enhancement.bidql["meta"]["model_enhancement"]["intent_summary"],
            "server tender search",
        )

    def test_failed_model_keeps_bidql_shape_and_records_meta(self) -> None:
        bidql = _bidql()
        gateway = FakeGateway(
            ModelCallResult(
                mode="cloud",
                provider="openai",
                model="test-model",
                status="failed",
                error="timeout",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            enhancement = enhance_bidql_with_model(settings, bidql, gateway=gateway)

        self.assertEqual(enhancement.bidql["topic"], bidql["topic"])
        self.assertEqual(enhancement.applied_keywords, [])
        self.assertNotIn("model", enhancement.bidql["meta"]["channels"])
        self.assertEqual(enhancement.bidql["meta"]["model_enhancement"]["status"], "failed")


def _bidql() -> dict[str, Any]:
    return {
        "version": "1.0",
        "query": "最近1个月上海服务器招标信息都有哪些",
        "topic": {
            "core": ["服务器"],
            "expanded": [{"term": "计算服务器", "weight": 0.92, "origin": "domain_dict"}],
            "negative": ["中标"],
            "origin": "rule",
        },
        "region": {"province": "上海"},
        "time": {"type": "relative_months"},
        "schedule": {"kind": "once"},
        "delivery": {"format": "docx", "channels": ["web", "outbox"]},
        "meta": {"channels": ["rule"], "confidence": {}},
    }


if __name__ == "__main__":
    unittest.main()
