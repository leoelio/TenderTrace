from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.integrations.feishu_bot import (
    accept_feishu_message_event,
    list_feishu_message_events,
    pending_feishu_message_event_ids,
    process_feishu_message_event,
)
from tendertrace.runner import RunOnceResult
from tendertrace.scheduling.subscriptions import Subscription


class FakeFeishuClient:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str]] = []

    def reply_text(self, message_id: str, text: str) -> dict:
        self.replies.append((message_id, text))
        return {"code": 0}


class FeishuBotTests(unittest.TestCase):
    def test_accepts_text_event_removes_mention_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            payload = _event_payload("evt-1", "msg-1", "@_user_1 最近一个月杭州服务器招标")

            first = accept_feishu_message_event(settings, payload)
            duplicate = accept_feishu_message_event(settings, payload)
            events = list_feishu_message_events(settings)

        self.assertEqual(first.status, "accepted")
        self.assertEqual(first.query, "最近一个月杭州服务器招标")
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(len(events), 1)

    def test_immediate_query_runs_and_targets_originating_chat(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(**kwargs) -> RunOnceResult:
            captured.update(kwargs)
            return RunOnceResult(
                run_id="run-1",
                status="finished",
                notice_count=3,
                docx_path="report.docx",
                outbox_path="outbox/report.docx",
                trace_events=4,
            )

        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            event = accept_feishu_message_event(
                settings,
                _event_payload("evt-run", "msg-run", "最近一个月杭州服务器招标"),
            )
            client = FakeFeishuClient()

            result = process_feishu_message_event(
                settings,
                event.event_id,
                client=client,
                run_func=fake_run,
            )
            repeated = process_feishu_message_event(
                settings,
                event.event_id,
                client=client,
                run_func=fake_run,
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.command_kind, "run")
        self.assertEqual(result.run_id, "run-1")
        self.assertEqual(captured["feishu_receive_id"], "oc_chat")
        self.assertEqual(captured["feishu_receive_id_type"], "chat_id")
        self.assertIn("3 条", client.replies[0][1])
        self.assertEqual(repeated.status, "completed")
        self.assertEqual(len(client.replies), 1)

    def test_scheduled_query_creates_chat_bound_incremental_subscription(self) -> None:
        captured: dict[str, object] = {}

        def fake_create(settings: Settings, **kwargs) -> Subscription:
            captured.update(kwargs)
            return Subscription(
                id="sub-1",
                original_query=str(kwargs["query"]),
                bidql={},
                schedule_kind="recurring",
                cron="0 9 * * *",
                timezone="Asia/Shanghai",
                status="active",
            )

        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            event = accept_feishu_message_event(
                settings,
                _event_payload(
                    "evt-sub",
                    "msg-sub",
                    "最近一个月上海服务器招标，每天9点发送给我",
                ),
            )
            client = FakeFeishuClient()

            result = process_feishu_message_event(
                settings,
                event.event_id,
                client=client,
                subscription_creator=fake_create,
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.command_kind, "subscription")
        self.assertEqual(result.subscription_id, "sub-1")
        self.assertEqual(captured["feishu_receive_id"], "oc_chat")
        self.assertIn("订阅已保存", client.replies[0][1])

    def test_non_text_message_is_audited_without_execution(self) -> None:
        payload = _event_payload("evt-file", "msg-file", "")
        payload["event"]["message"]["message_type"] = "file"
        with tempfile.TemporaryDirectory() as tmp:
            event = accept_feishu_message_event(Settings.load(Path(tmp)), payload)
        self.assertEqual(event.status, "ignored")

    def test_stale_processing_event_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            event = accept_feishu_message_event(
                settings,
                _event_payload("evt-stale", "msg-stale", "上海服务器招标"),
            )
            with connection(settings) as conn:
                conn.execute(
                    """
                    UPDATE feishu_message_events
                    SET status = 'processing', updated_at = datetime('now', '-20 minutes')
                    WHERE event_id = ?
                    """,
                    (event.event_id,),
                )

            pending = pending_feishu_message_event_ids(settings)

        self.assertEqual(pending, ["evt-stale"])

    def test_http_event_challenge_requires_matching_verification_token(self) -> None:
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = {
                "TENDERTRACE_DB_PATH": str(root / "data" / "db.sqlite3"),
                "TENDERTRACE_OUTPUTS_DIR": str(root / "outputs"),
                "TENDERTRACE_OUTBOX_DIR": str(root / "outbox"),
                "TENDERTRACE_SNAPSHOTS_DIR": str(root / "snapshots"),
                "TENDERTRACE_TRACES_DIR": str(root / "traces"),
                "TENDERTRACE_SECRETS_DIR": str(root / "secrets"),
                "TENDERTRACE_SCHEDULER_ENABLED": "false",
                "TENDERTRACE_MODEL_MODE": "local",
                "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED": "false",
                "FEISHU_ENABLED": "true",
                "FEISHU_APP_ID": "cli_test",
                "FEISHU_APP_SECRET": "secret-value",
                "FEISHU_CALLBACK_VERIFICATION_TOKEN": "verification-token",
            }
            previous = {key: os.environ.get(key) for key in values}
            os.environ.update(values)
            try:
                with TestClient(create_app()) as client:
                    accepted = client.post(
                        "/api/integrations/feishu/events",
                        json={"token": "verification-token", "challenge": "challenge-value"},
                    )
                    rejected = client.post(
                        "/api/integrations/feishu/events",
                        json={"token": "wrong", "challenge": "challenge-value"},
                    )
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json(), {"challenge": "challenge-value"})
        self.assertEqual(rejected.status_code, 401)


def _event_payload(event_id: str, message_id: str, text: str) -> dict:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "token": "verification-token",
        },
        "event": {
            "sender": {
                "sender_type": "user",
                "sender_id": {"open_id": "ou_sender"},
            },
            "message": {
                "message_id": message_id,
                "chat_id": "oc_chat",
                "chat_type": "group",
                "message_type": "text",
                "content": '{"text": "' + text + '"}',
                "mentions": [{"key": "@_user_1", "name": "TenderTrace"}],
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
