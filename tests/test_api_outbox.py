import os
from pathlib import Path
import tempfile
import unittest
import warnings

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.runlog import register_outbox_message, start_run


ENV_KEYS = (
    "TENDERTRACE_DB_PATH",
    "TENDERTRACE_OUTPUTS_DIR",
    "TENDERTRACE_OUTBOX_DIR",
    "TENDERTRACE_SNAPSHOTS_DIR",
    "TENDERTRACE_TRACES_DIR",
    "TENDERTRACE_SECRETS_DIR",
    "TENDERTRACE_SCHEDULER_ENABLED",
)


class OutboxApiTests(unittest.TestCase):
    def test_outbox_returns_tracked_run_id(self) -> None:
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
                settings = Settings.load()
                init_db(settings)
                start_run(
                    settings,
                    run_id="run-api-1",
                    original_query="最近1个月上海服务器招标信息",
                    mode="full",
                )
                settings.outbox_dir.mkdir(parents=True, exist_ok=True)
                docx_path = settings.outbox_dir / "report.docx"
                docx_path.write_bytes(b"placeholder")
                register_outbox_message(
                    settings,
                    run_id="run-api-1",
                    docx_path=docx_path,
                    message_id="message-api-1",
                )
                client = TestClient(create_app())
                response = client.get("/api/outbox")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["id"], "message-api-1")
        self.assertEqual(payload["items"][0]["run_id"], "run-api-1")
        self.assertEqual(payload["items"][0]["download_url"], "/api/outbox/report.docx")

    def test_delete_outbox_removes_file_and_tracking_record(self) -> None:
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
                settings = Settings.load()
                init_db(settings)
                start_run(
                    settings,
                    run_id="run-api-2",
                    original_query="最近1个月上海服务器招标信息",
                    mode="full",
                )
                settings.outbox_dir.mkdir(parents=True, exist_ok=True)
                docx_path = settings.outbox_dir / "delete-me.docx"
                docx_path.write_bytes(b"placeholder")
                register_outbox_message(
                    settings,
                    run_id="run-api-2",
                    docx_path=docx_path,
                    message_id="message-api-2",
                )
                client = TestClient(create_app())
                response = client.delete("/api/outbox/delete-me.docx")
                after = client.get("/api/outbox").json()
                exists = docx_path.exists()
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        self.assertFalse(exists)
        self.assertEqual(after["items"], [])


if __name__ == "__main__":
    unittest.main()
