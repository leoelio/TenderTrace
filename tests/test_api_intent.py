import os
from pathlib import Path
import tempfile
import unittest
import warnings


class IntentApiTests(unittest.TestCase):
    def test_parse_intent_accepts_json_body(self) -> None:
        warnings.filterwarnings(
            "ignore",
            message="Using `httpx` with `starlette.testclient` is deprecated.*",
        )
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        old_env = {
            key: os.environ.get(key)
            for key in (
                "TENDERTRACE_DB_PATH",
                "TENDERTRACE_OUTPUTS_DIR",
                "TENDERTRACE_OUTBOX_DIR",
                "TENDERTRACE_SNAPSHOTS_DIR",
                "TENDERTRACE_TRACES_DIR",
                "TENDERTRACE_SECRETS_DIR",
                "TENDERTRACE_SCHEDULER_ENABLED",
            )
        }
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
                client = TestClient(create_app())
                response = client.post(
                    "/api/intent/parse",
                    json={
                        "query": "2026年4月份上海的充电桩招标信息都有哪些，请汇总后今天9:00发送给我",
                        "now": "2026-07-06T10:00:00+08:00",
                    },
                )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["topic"]["core"], ["充电桩"])
        self.assertEqual(payload["region"]["province"], "上海")
        self.assertEqual(payload["schedule"]["kind"], "once_at")


if __name__ == "__main__":
    unittest.main()
