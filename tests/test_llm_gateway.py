from pathlib import Path
import os
import tempfile
import unittest
from typing import Any

from tendertrace.config import Settings
from tendertrace.llm.gateway import ModelGateway


MODEL_ENV_KEYS = (
    "TENDERTRACE_MODEL_MODE",
    "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED",
    "TENDERTRACE_MODEL_REQUEST_TIMEOUT",
    "TENDERTRACE_OLLAMA_BASE_URL",
    "TENDERTRACE_OLLAMA_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "TENDERTRACE_OPENAI_API_STYLE",
)


class FakeTransport:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {"url": url, "headers": headers, "payload": payload, "timeout": timeout}
        )
        return self.response


class ModelGatewayTests(unittest.TestCase):
    def test_local_ollama_payload_and_json_parse(self) -> None:
        with clean_model_env(), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=true\n"
                "TENDERTRACE_OLLAMA_MODEL=qwen3:8b\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
            transport = FakeTransport(
                {
                    "message": {
                        "content": (
                            '{"expanded_keywords":["GPU服务器"],'
                            '"negative_keywords":["中标"],"confidence":0.83}'
                        )
                    }
                }
            )

            result = ModelGateway(settings, transport=transport).generate_json(
                system="system",
                user="user",
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.parsed["expanded_keywords"], ["GPU服务器"])
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertTrue(call["url"].endswith("/api/chat"))
        self.assertEqual(call["payload"]["model"], "qwen3:8b")
        self.assertEqual(call["payload"]["format"], "json")
        self.assertNotIn("Authorization", call["headers"])

    def test_cloud_openai_responses_payload_is_redacted_from_result(self) -> None:
        with clean_model_env(), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_MODEL_MODE=cloud\n"
                "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=true\n"
                "OPENAI_API_KEY=test-key\n"
                "OPENAI_MODEL=test-model\n"
                "TENDERTRACE_OPENAI_API_STYLE=responses\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
            transport = FakeTransport(
                {
                    "output_text": (
                        '{"expanded_keywords":["储能系统"],'
                        '"negative_keywords":[],"confidence":0.91}'
                    )
                }
            )

            result = ModelGateway(settings, transport=transport).generate_json(
                system="system",
                user="user",
            )

        self.assertEqual(result.status, "ok")
        call = transport.calls[0]
        self.assertTrue(call["url"].endswith("/responses"))
        self.assertEqual(call["payload"]["model"], "test-model")
        self.assertFalse(call["payload"]["store"])
        self.assertEqual(call["headers"]["Authorization"], "Bearer test-key")
        self.assertNotIn("test-key", str(result.safe_dict()))

    def test_disabled_enhancement_skips_network(self) -> None:
        with clean_model_env(), tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            transport = FakeTransport({"message": {"content": "{}"}})

            result = ModelGateway(settings, transport=transport).generate_json(
                system="system",
                user="user",
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(transport.calls, [])


class clean_model_env:
    def __enter__(self) -> None:
        self.old_env = {key: os.environ.get(key) for key in MODEL_ENV_KEYS}
        for key in MODEL_ENV_KEYS:
            os.environ.pop(key, None)

    def __exit__(self, *_: object) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
