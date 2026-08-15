from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import warnings
from unittest.mock import patch


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


class OpportunityApiTests(unittest.TestCase):
    def test_action_endpoint_updates_stage_and_returns_gate_reasons(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module
        from tendertrace.config import Settings
        from tendertrace.db import connection, init_db

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
            os.environ["TENDERTRACE_API_TOKEN"] = ""
            try:
                settings = Settings.load()
                init_db(settings)
                with connection(settings) as conn:
                    conn.execute(
                        """
                        INSERT INTO notices(
                            id, source_site, source_url, canonical_url, title, purchaser,
                            publish_time, content_text, fields_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "notice-api-1",
                            "ccgp",
                            "https://example.com/notice-api-1",
                            "https://example.com/notice-api-1",
                            "服务器采购项目",
                            "示例采购人",
                            "2026-08-15",
                            "服务器采购项目，采购人为示例采购人。",
                            '{"bid_deadline":"2026-08-30 17:00"}',
                        ),
                    )
                with patch.object(
                    api_module,
                    "update_opportunity_workflow_in_bitable",
                    return_value=SimpleNamespace(status="skipped"),
                ):
                    client = TestClient(api_module.create_app())
                    claimed = client.post(
                        "/api/opportunities/notice-api-1/actions",
                        json={"action": "claim", "actor_name": "测试负责人"},
                    )
                    blocked = client.post(
                        "/api/opportunities/notice-api-1/actions",
                        json={"action": "prepare_bid", "actor_name": "测试负责人"},
                    )
                    escalation = client.post(
                        "/api/opportunities/escalations/send-feishu",
                        json={},
                    )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json()["workflow"]["stage"], "qualifying")
        self.assertEqual(claimed.json()["workflow"]["owner_name"], "测试负责人")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("当前阶段", blocked.json()["detail"]["reasons"][0])
        self.assertEqual(escalation.status_code, 200)
        self.assertEqual(escalation.json()["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
