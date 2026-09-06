import os
from pathlib import Path
import tempfile
import unittest
import warnings
from unittest.mock import patch

from tendertrace.organization_memory import OrganizationWorkspace
from tendertrace.runner import RunOnceResult


ENV_KEYS = (
    "TENDERTRACE_DB_PATH",
    "TENDERTRACE_OUTPUTS_DIR",
    "TENDERTRACE_OUTBOX_DIR",
    "TENDERTRACE_SNAPSHOTS_DIR",
    "TENDERTRACE_TRACES_DIR",
    "TENDERTRACE_SECRETS_DIR",
    "TENDERTRACE_SCHEDULER_ENABLED",
    "TENDERTRACE_API_TOKEN",
)


class RunsApiTests(unittest.TestCase):
    def test_create_run_returns_runner_result(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                workspace = OrganizationWorkspace(
                    id="workspace-1",
                    name="服务器项目群",
                    feishu_chat_id="oc_workspace_1",
                    status="active",
                    member_count=3,
                    memory_count=0,
                    created_by="admin",
                    created_at="2026-09-06 10:00:00",
                    updated_at="2026-09-06 10:00:00",
                )
                with patch.object(
                    api_module,
                    "run_once",
                    return_value=RunOnceResult(
                        run_id="run-api",
                        status="finished",
                        notice_count=1,
                        docx_path=str(root / "outputs" / "report.docx"),
                        outbox_path=str(root / "outbox" / "report.docx"),
                        trace_events=10,
                    ),
                ) as mocked, patch.object(
                    api_module,
                    "get_organization_workspace",
                    return_value=workspace,
                ):
                    client = TestClient(api_module.create_app())
                    response = client.post(
                        "/api/runs",
                        json={
                            "query": "最近1个月的上海区域内的服务器招标信息都有哪些",
                            "now": "2026-07-06T10:00:00+08:00",
                            "max_pages": 2,
                            "max_results": 5,
                            "model_strategy": "cloud",
                            "delivery_channels": ["web", "outbox", "feishu"],
                            "feishu_workspace_id": workspace.id,
                        },
                    )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run_id"], "run-api")
        self.assertEqual(response.json()["notice_count"], 1)
        self.assertEqual(mocked.call_args.kwargs["max_pages"], 2)
        self.assertEqual(mocked.call_args.kwargs["max_results"], 5)
        self.assertEqual(mocked.call_args.kwargs["model_strategy"], "cloud")
        self.assertEqual(mocked.call_args.kwargs["feishu_receive_id"], "oc_workspace_1")
        self.assertEqual(mocked.call_args.kwargs["feishu_receive_id_type"], "chat_id")

    def test_create_run_requires_query(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_env = {key: os.environ.get(key) for key in ENV_KEYS}
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                response = TestClient(create_app()).post("/api/runs", json={"query": ""})
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 400)

    def test_api_token_protects_write_routes_when_configured(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            os.environ["TENDERTRACE_API_TOKEN"] = "local-api-token"
            try:
                with patch.object(
                    api_module,
                    "run_once",
                    return_value=RunOnceResult(
                        run_id="run-token",
                        status="finished",
                        notice_count=0,
                        docx_path=None,
                        outbox_path=None,
                        trace_events=0,
                    ),
                ):
                    client = TestClient(api_module.create_app())
                    health_response = client.get("/api/health")
                    unauthorized = client.post("/api/runs", json={"query": "服务器招标"})
                    authorized = client.post(
                        "/api/runs",
                        json={"query": "服务器招标"},
                        headers={"X-TenderTrace-Token": "local-api-token"},
                    )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_start_run_returns_run_id_for_progress_polling(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                workspace = OrganizationWorkspace(
                    id="workspace-2",
                    name="充电桩项目群",
                    feishu_chat_id="oc_workspace_2",
                    status="active",
                    member_count=4,
                    memory_count=2,
                    created_by="admin",
                    created_at="2026-09-06 10:00:00",
                    updated_at="2026-09-06 10:00:00",
                )
                with patch.object(
                    api_module,
                    "run_once",
                    return_value=RunOnceResult(
                        run_id="ignored",
                        status="finished",
                        notice_count=0,
                        docx_path=None,
                        outbox_path=None,
                        trace_events=0,
                    ),
                ) as mocked, patch.object(
                    api_module,
                    "get_organization_workspace",
                    return_value=workspace,
                ):
                    client = TestClient(api_module.create_app())
                    response = client.post(
                        "/api/runs/start",
                        json={
                            "query": "最近36个月杭州市的空调或者服务器投标信息都有哪些",
                            "max_pages": 3,
                            "max_results": 8,
                            "model_strategy": "rules",
                            "delivery_channels": ["web", "outbox", "feishu"],
                            "feishu_workspace_id": workspace.id,
                        },
                    )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "queued")
        self.assertTrue(payload["run_id"])
        self.assertEqual(mocked.call_args.kwargs["run_id"], payload["run_id"])
        self.assertEqual(mocked.call_args.kwargs["model_strategy"], "rules")
        self.assertEqual(mocked.call_args.kwargs["feishu_receive_id"], "oc_workspace_2")
        self.assertEqual(mocked.call_args.kwargs["feishu_receive_id_type"], "chat_id")

    def test_run_rejects_unknown_feishu_workspace(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                response = TestClient(create_app()).post(
                    "/api/runs",
                    json={
                        "query": "最近1个月上海服务器招标信息",
                        "feishu_workspace_id": "missing-workspace",
                    },
                )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 404)

    def test_run_status_returns_compact_progress(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app
        from tendertrace.config import Settings
        from tendertrace.db import init_db
        from tendertrace.runlog import start_run
        from tendertrace.runtime.checkpoint import SqliteCheckpointer
        from tendertrace.runtime.state import RunState

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                settings = Settings.load()
                init_db(settings)
                start_run(
                    settings,
                    run_id="run-status",
                    original_query="server tender",
                    mode="full",
                )
                state = RunState.new("server tender", run_id="run-status")
                SqliteCheckpointer(settings).save(node="intent", state=state)
                client = TestClient(create_app())
                response = client.get("/api/runs/run-status/status")
                detail_response = client.get("/api/runs/run-status")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["progress"]["percent"], 25)
        self.assertEqual(payload["progress"]["current_node"], "intent")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("progress", detail_response.json())

    def test_runs_api_redacts_sensitive_stats(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app
        from tendertrace.config import Settings
        from tendertrace.db import init_db
        from tendertrace.runlog import finish_run, start_run

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                settings = Settings.load()
                init_db(settings)
                start_run(settings, run_id="run-secret", original_query="server", mode="full")
                finish_run(
                    settings,
                    run_id="run-secret",
                    status="finished",
                    output_docx_path=None,
                    stats={"feishu_bitable_delivery": {"app_token": "fixture-token"}},
                )
                client = TestClient(create_app())
                list_response = client.get("/api/runs")
                detail_response = client.get("/api/runs/run-secret")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotIn("fixture-token", str(list_response.json()))
        self.assertNotIn("fixture-token", str(detail_response.json()))
        self.assertEqual(
            list_response.json()["items"][0]["stats"]["feishu_bitable_delivery"]["app_token"],
            "[redacted]",
        )

    def test_delete_run_removes_history_record(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app
        from tendertrace.db import connection, init_db
        from tendertrace.runlog import start_run

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                from tendertrace.config import Settings

                settings = Settings.load()
                init_db(settings)
                start_run(
                    settings,
                    run_id="run-delete",
                    original_query="最近1个月上海服务器招标信息",
                    mode="full",
                )
                with connection(settings) as conn:
                    conn.execute(
                        """
                        INSERT INTO subscriptions(
                            id, original_query, bidql_json, schedule_kind, cron, timezone
                        )
                        VALUES (
                            'sub-delete',
                            '最近1个月上海服务器招标信息，每天9点发送',
                            '{}',
                            'recurring',
                            '0 9 * * *',
                            'Asia/Shanghai'
                        )
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO trace_events(run_id, seq, event_type, node)
                        VALUES ('run-delete', 1, 'node_started', 'intent')
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO sent_history(subscription_id, cluster_key, run_id, docx_path)
                        VALUES ('sub-delete', 'cluster-1', 'run-delete', 'outbox/report.docx')
                        """
                    )
                client = TestClient(create_app())
                before = client.get("/api/runs").json()["items"]
                response = client.delete("/api/runs/run-delete")
                after = client.get("/api/runs").json()["items"]
                detail_response = client.get("/api/runs/run-delete")
                with connection(settings) as conn:
                    deleted_status = conn.execute(
                        "SELECT status FROM runs WHERE id = 'run-delete'",
                    ).fetchone()["status"]
                    sent_history_count = conn.execute(
                        "SELECT COUNT(*) AS count FROM sent_history",
                    ).fetchone()["count"]
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        self.assertEqual(before[0]["id"], "run-delete")
        self.assertEqual(after, [])
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(deleted_status, "deleted")
        self.assertEqual(sent_history_count, 1)

    def test_agent_evaluation_returns_metric_sections(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        old_env = {key: os.environ.get(key) for key in ENV_KEYS}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "db.sqlite3")
            os.environ["TENDERTRACE_OUTPUTS_DIR"] = str(root / "outputs")
            os.environ["TENDERTRACE_OUTBOX_DIR"] = str(root / "outbox")
            os.environ["TENDERTRACE_SNAPSHOTS_DIR"] = str(root / "snapshots")
            os.environ["TENDERTRACE_TRACES_DIR"] = str(root / "traces")
            os.environ["TENDERTRACE_SECRETS_DIR"] = str(root / "secrets")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                response = TestClient(create_app()).get("/api/evaluations/agent")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("rag", payload)
        self.assertIn("agent", payload)
        self.assertIn("harness", payload)
        self.assertIn("recall", payload)
        self.assertIn("gold", payload)
        self.assertEqual(payload["status"], "incomplete")
        self.assertFalse(payload["evaluation_ready"])
        self.assertIn("gold_coverage", payload)
        self.assertEqual(payload["harness"]["case_count"], 4)
        self.assertEqual(payload["harness"]["passed_cases"], 4)
        self.assertIn("strict_recall_at_10", payload["recall"])
        self.assertIn("vector_coverage_rate", payload["recall"])


if __name__ == "__main__":
    unittest.main()
