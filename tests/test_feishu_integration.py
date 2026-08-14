from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
import warnings

import httpx

from tendertrace.config import Settings
from tendertrace.integrations.feishu import (
    FeishuClient,
    FeishuError,
    feishu_agent_status,
    feishu_status,
)


FEISHU_ENV_KEYS = (
    "FEISHU_ENABLED",
    "FEISHU_BASE_URL",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_DEFAULT_RECEIVE_ID",
    "FEISHU_DEFAULT_RECEIVE_ID_TYPE",
    "FEISHU_AGENT_ENABLED",
    "FEISHU_AGENT_BASE_URL",
    "FEISHU_AGENT_APP_ID",
    "FEISHU_AGENT_APP_SECRET",
)


class FeishuIntegrationTests(unittest.TestCase):
    def test_status_is_safe_and_secret_free(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".env.local").write_text(
                    "\n".join(
                        [
                            "FEISHU_ENABLED=true",
                            "FEISHU_APP_ID=cli_test",
                            "FEISHU_APP_SECRET=secret-value",
                            "FEISHU_DEFAULT_RECEIVE_ID=oc_test",
                        ]
                    ),
                    encoding="utf-8",
                )
                settings = Settings.load(root)
        finally:
            _restore_env(old_env)

        summary = settings.safe_summary()
        status = feishu_status(settings).to_dict()
        self.assertTrue(status["configured"])
        self.assertTrue(summary["feishu_message_app_secret_configured"])
        self.assertNotIn("secret-value", str(summary))
        self.assertNotIn("secret-value", str(status))

    def test_send_text_uses_tenant_token_and_message_endpoint(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".env.local").write_text(
                    "\n".join(
                        [
                            "FEISHU_ENABLED=true",
                            "FEISHU_APP_ID=cli_test",
                            "FEISHU_APP_SECRET=secret-value",
                            "FEISHU_DEFAULT_RECEIVE_ID=oc_test",
                            "FEISHU_DEFAULT_RECEIVE_ID_TYPE=chat_id",
                        ]
                    ),
                    encoding="utf-8",
                )
                settings = Settings.load(root)

                seen_paths: list[str] = []

                def handler(request: httpx.Request) -> httpx.Response:
                    seen_paths.append(request.url.path)
                    if request.url.path.endswith("/tenant_access_token/internal"):
                        payload = json.loads(request.content.decode("utf-8"))
                        self.assertEqual(payload["app_id"], "cli_test")
                        self.assertEqual(payload["app_secret"], "secret-value")
                        return httpx.Response(
                            200,
                            json={"code": 0, "msg": "ok", "tenant_access_token": "t-token"},
                        )
                    if request.url.path.endswith("/im/v1/messages"):
                        self.assertEqual(request.headers["Authorization"], "Bearer t-token")
                        self.assertEqual(request.url.params["receive_id_type"], "chat_id")
                        payload = json.loads(request.content.decode("utf-8"))
                        self.assertEqual(payload["receive_id"], "oc_test")
                        self.assertEqual(payload["msg_type"], "text")
                        self.assertEqual(json.loads(payload["content"])["text"], "TenderTrace test")
                        return httpx.Response(
                            200,
                            json={"code": 0, "msg": "ok", "data": {"message_id": "om_test"}},
                        )
                    return httpx.Response(404, json={"code": 404, "msg": "unexpected path"})

                client = httpx.Client(transport=httpx.MockTransport(handler))
                result = FeishuClient(settings, client=client).send_text("TenderTrace test")
        finally:
            _restore_env(old_env)

        self.assertEqual(result["data"]["message_id"], "om_test")
        self.assertEqual(
            seen_paths,
            [
                "/open-apis/auth/v3/tenant_access_token/internal",
                "/open-apis/im/v1/messages",
            ],
        )

    def test_disabled_client_does_not_call_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
        with self.assertRaises(FeishuError):
            FeishuClient(settings).send_text("hello", receive_id="oc_test")

    def test_agent_status_is_safe_and_secret_free(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".env.local").write_text(
                    "\n".join(
                        [
                            "FEISHU_AGENT_ENABLED=true",
                            "FEISHU_AGENT_APP_ID=cli_agent",
                            "FEISHU_AGENT_APP_SECRET=agent-secret",
                        ]
                    ),
                    encoding="utf-8",
                )
                status = feishu_agent_status(Settings.load(root)).to_dict()
        finally:
            _restore_env(old_env)

        self.assertTrue(status["configured"])
        self.assertTrue(status["app_secret_configured"])
        self.assertNotIn("agent-secret", str(status))

    def test_api_status_endpoint_is_secret_free(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        env_keys = FEISHU_ENV_KEYS + (
            "TENDERTRACE_DB_PATH",
            "TENDERTRACE_OUTPUTS_DIR",
            "TENDERTRACE_OUTBOX_DIR",
            "TENDERTRACE_SNAPSHOTS_DIR",
            "TENDERTRACE_TRACES_DIR",
            "TENDERTRACE_SECRETS_DIR",
            "TENDERTRACE_SCHEDULER_ENABLED",
            "TENDERTRACE_MODEL_MODE",
            "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED",
        )
        old_env = _clear_env(env_keys)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            os.environ["TENDERTRACE_MODEL_MODE"] = "local"
            os.environ["TENDERTRACE_MODEL_ENHANCEMENT_ENABLED"] = "false"
            os.environ["FEISHU_ENABLED"] = "false"
            os.environ["FEISHU_AGENT_ENABLED"] = "false"
            try:
                response = TestClient(create_app()).get("/api/integrations/feishu/status")
            finally:
                _restore_env(old_env)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["configured"])
        self.assertNotIn("secret-value", str(payload))


def _clear_env(keys: tuple[str, ...]) -> dict[str, str | None]:
    old_env = {key: os.environ.get(key) for key in keys}
    for key in keys:
        os.environ.pop(key, None)
    return old_env


def _restore_env(values: dict[str, str | None]) -> None:
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
