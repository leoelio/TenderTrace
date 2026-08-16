from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import warnings
from unittest.mock import patch


class OpportunityOutcomeApiTests(unittest.TestCase):
    def test_terminal_outcome_can_be_corrected_and_synced(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app import api as api_module
        from tendertrace.config import Settings
        from tendertrace.db import connection, init_db
        from tendertrace.workflow import update_workflow

        keys = (
            "TENDERTRACE_DB_PATH",
            "TENDERTRACE_OUTPUTS_DIR",
            "TENDERTRACE_OUTBOX_DIR",
            "TENDERTRACE_SCHEDULER_ENABLED",
            "TENDERTRACE_API_TOKEN",
        )
        old_env = {key: os.environ.get(key) for key in keys}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ.update(
                {
                    "TENDERTRACE_DB_PATH": str(root / "data" / "db.sqlite3"),
                    "TENDERTRACE_OUTPUTS_DIR": str(root / "outputs"),
                    "TENDERTRACE_OUTBOX_DIR": str(root / "outbox"),
                    "TENDERTRACE_SCHEDULER_ENABLED": "false",
                    "TENDERTRACE_API_TOKEN": "",
                }
            )
            try:
                settings = Settings.load()
                init_db(settings)
                with connection(settings) as conn:
                    conn.execute(
                        """
                        INSERT INTO notices(id, source_site, source_url, canonical_url, title)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            "notice-outcome-api",
                            "ccgp",
                            "https://example.com/notice",
                            "https://example.com/notice",
                            "服务器采购项目",
                        ),
                    )
                update_workflow(settings, "notice-outcome-api", stage="lost")
                with patch.object(
                    api_module,
                    "update_opportunity_workflow_in_bitable",
                    return_value=SimpleNamespace(status="sent", message=""),
                ):
                    client = TestClient(api_module.create_app())
                    response = client.put(
                        "/api/opportunities/notice-outcome-api/outcome",
                        json={
                            "actor_name": "销售经理",
                            "outcome": {
                                "result": "lost",
                                "reason_code": "price",
                                "winner_name": "示例竞争公司",
                                "award_amount": 880000,
                                "currency": "CNY",
                                "summary": "复核确认价格项为主要失标原因。",
                                "lessons": "提前完成成本拆解和报价审批。",
                                "evidence_url": "https://example.com/result",
                            },
                        },
                    )
                    mismatch = client.put(
                        "/api/opportunities/notice-outcome-api/outcome",
                        json={
                            "outcome": {
                                "result": "won",
                                "reason_code": "technical_fit",
                                "summary": "结果与当前阶段不一致。",
                                "lessons": "需要修正结果类型。",
                                "evidence_text": "内部复核记录。",
                            }
                        },
                    )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["outcome"]["result"], "lost")
        self.assertEqual(response.json()["bitable_status"], "sent")
        self.assertEqual(mismatch.status_code, 400)
        self.assertIn("must be lost", mismatch.json()["detail"])


if __name__ == "__main__":
    unittest.main()
