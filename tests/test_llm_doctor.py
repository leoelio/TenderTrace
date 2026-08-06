from pathlib import Path
import os
import tempfile
import unittest
from typing import Any

from tendertrace.config import Settings
from tendertrace.llm.doctor import model_doctor
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


class RaisingTransport:
    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        fake_key = "sk-proj-" + "THIS_SHOULD_NOT_LEAK"
        raise RuntimeError(f"provider rejected Bearer {fake_key}")


class ModelDoctorTests(unittest.TestCase):
    def test_cloud_mode_does_not_require_local_ollama(self) -> None:
        with clean_model_env(), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_MODEL_MODE=cloud\n"
                "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=false\n"
                "OPENAI_API_KEY=secret-value\n"
                "OPENAI_MODEL=test-model\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)

            report = model_doctor(settings)

        self.assertEqual(report.status, "pass")
        payload = report.to_dict()
        self.assertIn("Ollama is not required", str(payload))
        self.assertNotIn("secret-value", str(payload))

    def test_local_live_probe_uses_ollama_and_requires_json(self) -> None:
        with clean_model_env(), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_MODEL_MODE=local\n"
                "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=true\n"
                "TENDERTRACE_OLLAMA_MODEL=qwen3:8b\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
            transport = FakeTransport({"message": {"content": '{"ok": true}'}})
            gateway = ModelGateway(settings, transport=transport)

            report = model_doctor(settings, live=True, gateway=gateway)

        self.assertEqual(report.status, "pass")
        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["live_probe"].status, "pass")
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(transport.calls[0]["url"].endswith("/api/chat"))
        self.assertEqual(transport.calls[0]["payload"]["model"], "qwen3:8b")

    def test_live_probe_failure_is_redacted(self) -> None:
        with clean_model_env(), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_MODEL_MODE=cloud\n"
                "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=true\n"
                "OPENAI_API_KEY=" + "sk-proj-" + "REAL_SECRET_VALUE\n"
                "OPENAI_MODEL=test-model\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
            gateway = ModelGateway(settings, transport=RaisingTransport())

            report = model_doctor(settings, live=True, gateway=gateway)

        self.assertEqual(report.status, "fail")
        text = str(report.to_dict())
        self.assertIn("Bearer [redacted]", text)
        self.assertNotIn("REAL_SECRET_VALUE", text)


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
