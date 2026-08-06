from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.scheduling.ledger import mark_sent, unsent_cluster_keys


class SentHistoryTests(unittest.TestCase):
    def test_sent_history_prevents_duplicate_cluster_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            with connection(settings) as conn:
                conn.execute(
                    """
                    INSERT INTO subscriptions(id, original_query, bidql_json, schedule_kind, timezone)
                    VALUES ('sub-1', 'q', '{}', 'recurring', 'Asia/Shanghai')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO runs(id, subscription_id, original_query, mode, status)
                    VALUES ('run-1', 'sub-1', 'q', 'incremental', 'finished')
                    """
                )
                self.assertTrue(
                    mark_sent(
                        conn,
                        subscription_id="sub-1",
                        cluster_key="pno:abc",
                        run_id="run-1",
                        docx_path="outbox/report.docx",
                    )
                )
                self.assertFalse(
                    mark_sent(
                        conn,
                        subscription_id="sub-1",
                        cluster_key="pno:abc",
                        run_id="run-1",
                        docx_path="outbox/report.docx",
                    )
                )
                unsent = unsent_cluster_keys(
                    conn,
                    subscription_id="sub-1",
                    cluster_keys=["pno:abc", "pno:def", "pno:def"],
                )
        self.assertEqual(unsent, ["pno:def"])


if __name__ == "__main__":
    unittest.main()
