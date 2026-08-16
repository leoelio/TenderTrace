import os
from pathlib import Path
import tempfile
import unittest
import warnings


ENV_KEYS = (
    "TENDERTRACE_DB_PATH",
    "TENDERTRACE_OUTPUTS_DIR",
    "TENDERTRACE_OUTBOX_DIR",
    "TENDERTRACE_SNAPSHOTS_DIR",
    "TENDERTRACE_TRACES_DIR",
    "TENDERTRACE_SECRETS_DIR",
    "TENDERTRACE_SCHEDULER_ENABLED",
    "TENDERTRACE_MODEL_MODE",
    "TENDERTRACE_MODEL_ENHANCEMENT_ENABLED",
    "OPENAI_API_KEY",
)


class SourcesApiTests(unittest.TestCase):
    def test_sources_reports_public_sources_and_qianlima_login_state(self) -> None:
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
            os.environ["TENDERTRACE_MODEL_MODE"] = "local"
            os.environ["TENDERTRACE_MODEL_ENHANCEMENT_ENABLED"] = "false"
            try:
                client = TestClient(create_app())
                response = client.get("/api/sources")
                alert_response = client.get("/api/sources/alerts")
                incidents_response = client.get("/api/sources/incidents")
                incident_sync_response = client.post("/api/sources/incidents/sync", json={})
                source_map_response = client.get("/api/source-map")
                model_response = client.get("/api/model")
                doctor_response = client.get("/api/model/doctor")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(
            [item["site"] for item in items],
            [
                "ccgp",
                "ggzy",
                "ted",
                "ungm",
                "worldbank",
                "idb",
                "adb",
                "afdb",
                "ebrd",
                "contracts_finder",
                "find_tender",
                "canadabuys",
                "prozorro",
                "qianlima",
            ],
        )
        self.assertEqual(items[0]["status"], "configured")
        self.assertEqual(items[1]["status"], "configured")
        self.assertEqual(items[2]["status"], "configured")
        self.assertEqual(items[3]["status"], "configured")
        self.assertEqual(items[4]["status"], "configured")
        self.assertEqual(items[5]["status"], "configured")
        self.assertEqual(items[6]["status"], "configured")
        self.assertEqual(items[7]["status"], "configured")
        self.assertEqual(items[8]["status"], "configured")
        self.assertEqual(items[9]["status"], "configured")
        self.assertEqual(items[-1]["status"], "login_required")
        self.assertEqual(items[-1]["validation"], "missing")
        self.assertFalse(items[-1]["ready"])
        self.assertIn("routes", items[0])
        self.assertIn("health", items[0])
        self.assertIn("discovery_rules", items[0])
        self.assertEqual(alert_response.status_code, 200)
        self.assertEqual(alert_response.json()["status"], "healthy")
        self.assertEqual(alert_response.json()["issue_count"], 0)
        self.assertFalse(alert_response.json()["delivery_ready"])
        self.assertIsInstance(alert_response.json()["task_ready"], bool)
        self.assertFalse(alert_response.json()["task_assignee_ready"])
        self.assertEqual(alert_response.json()["incident_sla_hours"], 4)
        self.assertEqual(alert_response.json()["incident_summary"]["active_count"], 0)
        self.assertEqual(incidents_response.status_code, 200)
        self.assertEqual(incidents_response.json(), {"items": [], "active_count": 0})
        self.assertEqual(incident_sync_response.status_code, 200)
        self.assertEqual(incident_sync_response.json()["status"], "skipped")
        self.assertEqual(source_map_response.status_code, 200)
        source_map_payload = source_map_response.json()
        self.assertEqual(source_map_payload["source_count"], 14)
        self.assertFalse(source_map_payload["login_source_ready"])
        self.assertTrue(source_map_payload["items"][-1]["requires_login"])
        self.assertEqual(model_response.status_code, 200)
        model_payload = model_response.json()
        self.assertEqual(model_payload["mode"], "local")
        self.assertEqual(model_payload["provider"], "ollama")
        self.assertIn("configured", model_payload)
        self.assertNotIn("api_key", str(model_payload).lower())
        self.assertEqual(doctor_response.status_code, 200)
        doctor_payload = doctor_response.json()
        self.assertEqual(doctor_payload["status"], "pass")
        self.assertFalse(doctor_payload["live"])
        self.assertNotIn("api_key", str(doctor_payload).lower())


if __name__ == "__main__":
    unittest.main()
