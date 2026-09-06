import os
import json
from pathlib import Path
import tempfile
import unittest
import warnings
from unittest.mock import patch

from tendertrace.organization_memory import OrganizationWorkspace
from tendertrace.runner import RunOnceResult
from tendertrace.scheduling.subscriptions import Subscription


ENV_KEYS = (
    "TENDERTRACE_DB_PATH",
    "TENDERTRACE_OUTPUTS_DIR",
    "TENDERTRACE_OUTBOX_DIR",
    "TENDERTRACE_SNAPSHOTS_DIR",
    "TENDERTRACE_TRACES_DIR",
    "TENDERTRACE_SECRETS_DIR",
    "TENDERTRACE_SCHEDULER_ENABLED",
)


class SubscriptionApiTests(unittest.TestCase):
    def test_create_subscription_returns_schedule_contract(self) -> None:
        client, cleanup = _client()
        try:
            response = client.post(
                "/api/subscriptions",
                json={
                    "query": "最近1个月的上海区域内的服务器招标信息都有哪些，请汇总后每天9:00发送给我",
                    "now": "2026-07-06T10:00:00+08:00",
                    "max_pages": 2,
                    "max_results": 5,
                },
            )
        finally:
            cleanup()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schedule_kind"], "recurring")
        self.assertEqual(payload["cron"], "0 9 * * *")
        self.assertEqual(payload["bidql"]["_runtime"], {"max_pages": 2, "max_results": 5})

    def test_create_subscription_accepts_ui_schedule_and_model_strategy(self) -> None:
        client, cleanup = _client()
        try:
            from tendertrace.app import api as api_module

            workspace = OrganizationWorkspace(
                id="workspace-subscription",
                name="空调项目群",
                feishu_chat_id="oc_workspace_subscription",
                status="active",
                member_count=2,
                memory_count=1,
                created_by="admin",
                created_at="2026-09-06 10:00:00",
                updated_at="2026-09-06 10:00:00",
            )
            with patch.object(
                api_module,
                "get_organization_workspace",
                return_value=workspace,
            ):
                response = client.post(
                    "/api/subscriptions",
                    json={
                        "query": "最近36个月杭州市的空调或者服务器投标信息都有哪些",
                        "now": "2026-07-06T10:00:00+08:00",
                        "max_pages": 3,
                        "max_results": 8,
                        "model_strategy": "hybrid",
                        "delivery_channels": ["web", "outbox", "feishu"],
                        "feishu_workspace_id": workspace.id,
                        "schedule": {
                            "kind": "recurring",
                            "frequency": "daily",
                            "time": "08:45",
                        },
                    },
                )
        finally:
            cleanup()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schedule_kind"], "recurring")
        self.assertEqual(payload["cron"], "45 8 * * *")
        self.assertEqual(payload["bidql"]["schedule"]["origin"], "ui_override")
        self.assertEqual(payload["bidql"]["_runtime"]["model_strategy"], "hybrid")
        self.assertEqual(
            payload["bidql"]["_runtime"]["feishu_receive_id"],
            "oc_workspace_subscription",
        )
        self.assertEqual(payload["bidql"]["_runtime"]["feishu_receive_id_type"], "chat_id")

    def test_create_subscription_rejects_immediate_query(self) -> None:
        client, cleanup = _client()
        try:
            response = client.post(
                "/api/subscriptions",
                json={"query": "最近1个月的上海区域内的服务器招标信息都有哪些"},
            )
        finally:
            cleanup()

        self.assertEqual(response.status_code, 400)

    def test_run_subscription_returns_runner_result(self) -> None:
        client, cleanup = _client()
        try:
            with patch(
                "tendertrace.app.api.run_subscription",
                return_value=RunOnceResult(
                    run_id="run-sub",
                    status="finished",
                    notice_count=0,
                    docx_path="outputs/report.docx",
                    outbox_path="outbox/report.docx",
                    trace_events=10,
                ),
            ) as mocked:
                response = client.post("/api/subscriptions/sub-1/run")
        finally:
            cleanup()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run_id"], "run-sub")
        self.assertEqual(mocked.call_args.kwargs["subscription_id"], "sub-1")

    def test_list_subscriptions_returns_items(self) -> None:
        client, cleanup = _client()
        try:
            with patch(
                "tendertrace.app.api.list_subscriptions",
                return_value=[
                    Subscription(
                        id="sub-1",
                        original_query="每天9:00发送服务器招标信息",
                        bidql={"schedule": {"kind": "recurring"}},
                        schedule_kind="recurring",
                        cron="0 9 * * *",
                        timezone="Asia/Shanghai",
                        status="active",
                    )
                ],
            ):
                response = client.get("/api/subscriptions")
        finally:
            cleanup()

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], "sub-1")
        self.assertIn("next_run_at", item)
        self.assertEqual(item["last_notice_count"], 0)
        self.assertEqual(item["last_new_count"], 0)
        self.assertEqual(item["last_skipped_sent"], 0)
        self.assertIsNone(item["last_download_url"])

    def test_list_subscriptions_includes_latest_run_outbox_and_email_summary(self) -> None:
        client, cleanup = _client()
        try:
            from tendertrace.config import Settings
            from tendertrace.db import connection, init_db

            settings = Settings.load()
            init_db(settings)
            report = settings.outbox_dir / "latest.docx"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_bytes(b"docx")
            stats = {
                "notice_count": 5,
                "new": 2,
                "skipped_sent": 3,
                "email_delivery": {"status": "sent"},
                "feishu_bitable_delivery": {"app_token": "fixture-token"},
            }
            with connection(settings) as conn:
                conn.execute(
                    """
                    INSERT INTO subscriptions (
                        id, original_query, bidql_json, schedule_kind, cron, timezone, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "sub-1",
                        "每天9:00发送服务器招标信息",
                        json.dumps({"schedule": {"kind": "recurring"}}),
                        "recurring",
                        "0 9 * * *",
                        "Asia/Shanghai",
                        "active",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO runs (
                        id, subscription_id, original_query, mode, status,
                        started_at, finished_at, output_docx_path, stats_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "run-latest",
                        "sub-1",
                        "每天9:00发送服务器招标信息",
                        "subscription",
                        "finished",
                        "2026-08-06 08:59:00",
                        "2026-08-06 09:00:00",
                        str(report),
                        json.dumps(stats),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO outbox_messages (id, run_id, subscription_id, docx_path, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("msg-1", "run-latest", "sub-1", str(report), "ready"),
                )
            with patch(
                "tendertrace.app.api.list_subscriptions",
                return_value=[
                    Subscription(
                        id="sub-1",
                        original_query="每天9:00发送服务器招标信息",
                        bidql={"schedule": {"kind": "recurring"}},
                        schedule_kind="recurring",
                        cron="0 9 * * *",
                        timezone="Asia/Shanghai",
                        status="active",
                    )
                ],
            ):
                response = client.get("/api/subscriptions")
        finally:
            cleanup()

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["last_run_id"], "run-latest")
        self.assertEqual(item["last_run_finished_at"], "2026-08-06 09:00:00")
        self.assertEqual(item["last_notice_count"], 5)
        self.assertEqual(item["last_new_count"], 2)
        self.assertEqual(item["last_skipped_sent"], 3)
        self.assertEqual(item["last_outbox_name"], "latest.docx")
        self.assertEqual(item["last_download_url"], "/api/outbox/latest.docx")
        self.assertEqual(item["last_email_status"], "sent")
        self.assertNotIn("fixture-token", str(item))

    def test_delete_subscription_hides_it_from_active_list(self) -> None:
        client, cleanup = _client()
        try:
            create_response = client.post(
                "/api/subscriptions",
                json={
                    "query": "最近1个月上海服务器招标信息都有哪些，请每天9:00发送给我",
                    "max_pages": 1,
                    "max_results": 5,
                },
            )
            subscription_id = create_response.json()["id"]
            delete_response = client.delete(f"/api/subscriptions/{subscription_id}")
            list_response = client.get("/api/subscriptions")
        finally:
            cleanup()

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["status"], "deleted")
        self.assertEqual(list_response.json()["items"], [])


def _client():
    warnings.filterwarnings(
        "ignore",
        message="Using `httpx` with `starlette.testclient` is deprecated.*",
    )
    from fastapi.testclient import TestClient

    from tendertrace.app.api import create_app

    old_env = {key: os.environ.get(key) for key in ENV_KEYS}
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
    os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
    os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
    os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
    os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
    os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
    os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"

    def cleanup() -> None:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tmp.cleanup()

    return TestClient(create_app()), cleanup


if __name__ == "__main__":
    unittest.main()
