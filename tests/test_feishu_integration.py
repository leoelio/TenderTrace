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
    "FEISHU_CALENDAR_ID",
    "FEISHU_CALLBACK_VERIFICATION_TOKEN",
    "TENDERTRACE_FEISHU_TASK_SYNC_ENABLED",
    "TENDERTRACE_FEISHU_TASK_SYNC_CRON",
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

    def test_reply_text_uses_official_reply_endpoint(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".env.local").write_text(
                    "FEISHU_ENABLED=true\n"
                    "FEISHU_APP_ID=cli_test\n"
                    "FEISHU_APP_SECRET=secret-value\n",
                    encoding="utf-8",
                )
                settings = Settings.load(root)

                def handler(request: httpx.Request) -> httpx.Response:
                    if request.url.path.endswith("/tenant_access_token/internal"):
                        return httpx.Response(
                            200,
                            json={"code": 0, "tenant_access_token": "t-token"},
                        )
                    self.assertEqual(
                        request.url.path,
                        "/open-apis/im/v1/messages/om_origin/reply",
                    )
                    payload = json.loads(request.content.decode("utf-8"))
                    self.assertEqual(payload["msg_type"], "text")
                    self.assertEqual(json.loads(payload["content"])["text"], "检索已开始")
                    return httpx.Response(
                        200,
                        json={"code": 0, "data": {"message_id": "om_reply"}},
                    )

                result = FeishuClient(
                    settings,
                    client=httpx.Client(transport=httpx.MockTransport(handler)),
                ).reply_text("om_origin", "检索已开始")
        finally:
            _restore_env(old_env)

        self.assertEqual(result["data"]["message_id"], "om_reply")

    def test_card_task_read_and_calendar_use_official_endpoints(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".env.local").write_text(
                    "FEISHU_ENABLED=true\n"
                    "FEISHU_APP_ID=cli_test\n"
                    "FEISHU_APP_SECRET=secret-value\n"
                    "FEISHU_DEFAULT_RECEIVE_ID=oc_test\n",
                    encoding="utf-8",
                )
                settings = Settings.load(root)
                seen: list[str] = []

                def handler(request: httpx.Request) -> httpx.Response:
                    seen.append(request.url.path)
                    if request.url.path.endswith("/tenant_access_token/internal"):
                        return httpx.Response(
                            200,
                            json={"code": 0, "tenant_access_token": "t-token"},
                        )
                    payload = json.loads(request.content.decode("utf-8")) if request.content else {}
                    if request.url.path.endswith("/im/v1/messages"):
                        self.assertEqual(payload["msg_type"], "interactive")
                        self.assertEqual(json.loads(payload["content"])["header"]["template"], "blue")
                        return httpx.Response(
                            200,
                            json={"code": 0, "data": {"message_id": "om-card"}},
                        )
                    if request.url.path.endswith("/task/v2/tasks"):
                        self.assertEqual(payload["client_token"], "task-token")
                        self.assertEqual(payload["reminders"], [{"relative_fire_minute": 60}])
                        return httpx.Response(
                            200,
                            json={"code": 0, "data": {"task": {"guid": "task-guid"}}},
                        )
                    if request.url.path.endswith("/task/v2/tasks/task-guid"):
                        self.assertEqual(request.method, "GET")
                        self.assertEqual(request.url.params["user_id_type"], "open_id")
                        return httpx.Response(
                            200,
                            json={"code": 0, "data": {"task": {"guid": "task-guid", "completed_at": "0"}}},
                        )
                    if request.url.path.endswith("/calendar/v4/calendars/primary/events"):
                        self.assertEqual(request.url.params["idempotency_key"], "calendar-token")
                        return httpx.Response(
                            200,
                            json={"code": 0, "data": {"event": {"event_id": "event-id"}}},
                        )
                    return httpx.Response(404, json={"code": 404, "msg": "unexpected"})

                client = FeishuClient(
                    settings,
                    client=httpx.Client(transport=httpx.MockTransport(handler)),
                )
                card = client.send_card({"header": {"template": "blue"}})
                task = client.create_task(
                    summary="跟进机会",
                    description="核对预算",
                    client_token="task-token",
                    due_timestamp_ms="1786845600000",
                    reminder_minutes=60,
                )
                fetched_task = client.get_task("task-guid")
                event = client.create_calendar_event(
                    calendar_id="primary",
                    summary="投标截止",
                    description="截止提醒",
                    start_timestamp="1788051600",
                    end_timestamp="1788053400",
                    idempotency_key="calendar-token",
                )
        finally:
            _restore_env(old_env)

        self.assertEqual(card["data"]["message_id"], "om-card")
        self.assertEqual(task["data"]["task"]["guid"], "task-guid")
        self.assertEqual(fetched_task["data"]["task"]["completed_at"], "0")
        self.assertEqual(event["data"]["event"]["event_id"], "event-id")
        self.assertIn("/open-apis/task/v2/tasks", seen)

    def test_authorized_directory_and_task_assignment_use_official_endpoints(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".env.local").write_text(
                    "FEISHU_ENABLED=true\n"
                    "FEISHU_APP_ID=cli_test\n"
                    "FEISHU_APP_SECRET=secret-value\n",
                    encoding="utf-8",
                )
                settings = Settings.load(root)
                seen: list[str] = []

                def handler(request: httpx.Request) -> httpx.Response:
                    seen.append(request.url.path)
                    if request.url.path.endswith("/tenant_access_token/internal"):
                        return httpx.Response(
                            200,
                            json={"code": 0, "tenant_access_token": "t-token"},
                        )
                    if request.url.path.endswith("/contact/v3/scopes"):
                        self.assertEqual(request.url.params["user_id_type"], "open_id")
                        return httpx.Response(
                            200,
                            json={
                                "code": 0,
                                "data": {
                                    "user_ids": ["ou_owner"],
                                    "department_ids": [],
                                    "has_more": False,
                                },
                            },
                        )
                    if request.url.path.endswith("/contact/v3/users/batch"):
                        self.assertEqual(request.url.params.get_list("user_ids"), ["ou_owner"])
                        return httpx.Response(
                            200,
                            json={
                                "code": 0,
                                "data": {
                                    "items": [
                                        {
                                            "open_id": "ou_owner",
                                            "name": "张三",
                                            "email": "private@example.com",
                                            "department_ids": ["od_sales"],
                                            "status": {
                                                "is_activated": True,
                                                "is_resigned": False,
                                            },
                                        }
                                    ]
                                },
                            },
                        )
                    if request.url.path.endswith("/task/v2/tasks/task-guid/add_members"):
                        body = json.loads(request.content.decode("utf-8"))
                        self.assertEqual(
                            body["members"],
                            [{"type": "user", "id": "ou_owner", "role": "assignee"}],
                        )
                        return httpx.Response(200, json={"code": 0, "data": {}})
                    return httpx.Response(404, json={"code": 404, "msg": "unexpected"})

                client = FeishuClient(
                    settings,
                    client=httpx.Client(transport=httpx.MockTransport(handler)),
                )
                directory = client.list_authorized_users()
                assigned = client.add_task_members(
                    "task-guid",
                    assignee_open_ids=["ou_owner", "ou_owner"],
                )
        finally:
            _restore_env(old_env)

        self.assertEqual(directory["returned_count"], 1)
        self.assertEqual(directory["items"][0]["name"], "张三")
        self.assertNotIn("email", directory["items"][0])
        self.assertEqual(assigned["code"], 0)
        self.assertIn("/open-apis/contact/v3/scopes", seen)
        self.assertIn("/open-apis/task/v2/tasks/task-guid/add_members", seen)

    def test_authorized_directory_expands_department_scope(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".env.local").write_text(
                    "FEISHU_ENABLED=true\n"
                    "FEISHU_APP_ID=cli_test\n"
                    "FEISHU_APP_SECRET=secret-value\n",
                    encoding="utf-8",
                )
                settings = Settings.load(root)

                def handler(request: httpx.Request) -> httpx.Response:
                    path = request.url.path
                    if path.endswith("/tenant_access_token/internal"):
                        return httpx.Response(
                            200,
                            json={"code": 0, "tenant_access_token": "t-token"},
                        )
                    if path.endswith("/contact/v3/scopes"):
                        return httpx.Response(
                            200,
                            json={
                                "code": 0,
                                "data": {
                                    "user_ids": [],
                                    "department_ids": ["od_sales"],
                                    "has_more": False,
                                },
                            },
                        )
                    if path.endswith("/departments/od_sales/children"):
                        return httpx.Response(
                            200,
                            json={
                                "code": 0,
                                "data": {
                                    "items": [{"open_department_id": "od_enterprise"}],
                                    "has_more": False,
                                },
                            },
                        )
                    if path.endswith("/users/find_by_department"):
                        department_id = request.url.params["department_id"]
                        items = (
                            [{"open_id": "ou_sales", "name": "销售负责人"}]
                            if department_id == "od_sales"
                            else [{"open_id": "ou_solution", "name": "解决方案经理"}]
                        )
                        return httpx.Response(
                            200,
                            json={"code": 0, "data": {"items": items, "has_more": False}},
                        )
                    return httpx.Response(404, json={"code": 404, "msg": "unexpected"})

                directory = FeishuClient(
                    settings,
                    client=httpx.Client(transport=httpx.MockTransport(handler)),
                ).list_authorized_users()
        finally:
            _restore_env(old_env)

        self.assertEqual(directory["authorized_department_count"], 1)
        self.assertEqual(directory["returned_count"], 2)
        self.assertEqual(
            {item["open_id"] for item in directory["items"]},
            {"ou_sales", "ou_solution"},
        )

    def test_disabled_client_does_not_call_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
        with self.assertRaises(FeishuError):
            FeishuClient(settings).send_text("hello", receive_id="oc_test")

    def test_platform_error_has_actionable_message(self) -> None:
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
                        ]
                    ),
                    encoding="utf-8",
                )
                settings = Settings.load(root)

                def handler(request: httpx.Request) -> httpx.Response:
                    if request.url.path.endswith("/tenant_access_token/internal"):
                        return httpx.Response(
                            200,
                            json={"code": 0, "tenant_access_token": "t-token"},
                        )
                    return httpx.Response(
                        400,
                        json={"code": 232034, "msg": "app unavailable"},
                    )

                client = httpx.Client(transport=httpx.MockTransport(handler))
                with self.assertRaisesRegex(FeishuError, "发布应用"):
                    FeishuClient(settings, client=client).list_chats()
        finally:
            _restore_env(old_env)

    def test_send_file_uploads_docx_then_sends_file_message(self) -> None:
        old_env = _clear_env(FEISHU_ENV_KEYS)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                report = root / "report.docx"
                report.write_bytes(b"docx-content")
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
                        return httpx.Response(
                            200,
                            json={"code": 0, "tenant_access_token": "t-token"},
                        )
                    if request.url.path.endswith("/im/v1/files"):
                        self.assertIn("multipart/form-data", request.headers["Content-Type"])
                        body = request.content.decode("latin-1")
                        self.assertIn('name="file_type"', body)
                        self.assertIn("stream", body)
                        self.assertIn("report.docx", body)
                        return httpx.Response(
                            200,
                            json={"code": 0, "data": {"file_key": "file-test"}},
                        )
                    if request.url.path.endswith("/im/v1/messages"):
                        payload = json.loads(request.content.decode("utf-8"))
                        self.assertEqual(payload["msg_type"], "file")
                        self.assertEqual(json.loads(payload["content"]), {"file_key": "file-test"})
                        return httpx.Response(
                            200,
                            json={"code": 0, "data": {"message_id": "om-file"}},
                        )
                    return httpx.Response(404, json={"code": 404, "msg": "unexpected"})

                client = httpx.Client(transport=httpx.MockTransport(handler))
                result = FeishuClient(settings, client=client).send_file(report)
        finally:
            _restore_env(old_env)

        self.assertEqual(result["data"]["message_id"], "om-file")
        self.assertEqual(
            seen_paths,
            [
                "/open-apis/auth/v3/tenant_access_token/internal",
                "/open-apis/im/v1/files",
                "/open-apis/auth/v3/tenant_access_token/internal",
                "/open-apis/im/v1/messages",
            ],
        )

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
