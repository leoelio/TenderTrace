from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import SCHEMA_VERSION, database_health, init_db


class DatabaseTests(unittest.TestCase):
    def test_init_db_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            init_db(settings)
            health = database_health(settings)
        self.assertTrue(health["initialized"])
        self.assertIn("sent_history", health["tables"])
        self.assertIn("evidence_items", health["tables"])
        self.assertIn("attachment_snapshots", health["tables"])
        self.assertIn("page_artifacts", health["tables"])
        self.assertIn("model_audits", health["tables"])
        self.assertIn("run_checkpoints", health["tables"])
        self.assertIn("notices_fts", health["tables"])
        self.assertIn("ingest_subscriptions", health["tables"])
        self.assertIn("notice_embeddings", health["tables"])
        self.assertIn("notice_revisions", health["tables"])
        self.assertIn("user_activity_events", health["tables"])
        self.assertIn("weekly_reports", health["tables"])
        self.assertIn("user_memory_profiles", health["tables"])
        self.assertIn("memory_advice_feedback", health["tables"])
        self.assertIn("opportunity_fact_overrides", health["tables"])
        self.assertIn("opportunity_workflows", health["tables"])
        self.assertIn("opportunity_events", health["tables"])
        self.assertIn("feishu_lead_import_runs", health["tables"])
        self.assertIn("feishu_message_events", health["tables"])
        self.assertIn("source_incidents", health["tables"])
        self.assertIn(SCHEMA_VERSION, health["schema_versions"])


if __name__ == "__main__":
    unittest.main()
