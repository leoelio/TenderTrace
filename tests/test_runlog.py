from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.runlog import (
    finish_run,
    get_run,
    list_outbox_messages,
    register_outbox_message,
    start_run,
)


class RunLogTests(unittest.TestCase):
    def test_run_and_outbox_are_traceable_by_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            init_db(settings)
            run_id = "run-1"

            start_run(
                settings,
                run_id=run_id,
                original_query="最近1个月上海服务器招标信息",
                mode="full",
                window_start="2026-06-06",
                window_end="2026-07-06",
            )
            docx_path = settings.outbox_dir / "report.docx"
            settings.outbox_dir.mkdir(parents=True, exist_ok=True)
            docx_path.write_bytes(b"placeholder")
            register_outbox_message(settings, run_id=run_id, docx_path=docx_path, message_id="m1")
            finish_run(
                settings,
                run_id=run_id,
                status="finished",
                output_docx_path=docx_path,
                stats={"notice_count": 1, "feishu_bitable_delivery": {"app_token": "fixture-token"}},
            )

            run = get_run(settings, run_id)
            messages = list_outbox_messages(settings)
            with connection(settings) as conn:
                row = conn.execute(
                    "SELECT output_docx_path FROM runs WHERE id = ?",
                    (run_id,),
                ).fetchone()

        self.assertEqual(run["status"], "finished")
        self.assertEqual(run["stats"]["notice_count"], 1)
        self.assertEqual(run["stats"]["feishu_bitable_delivery"]["app_token"], "[redacted]")
        self.assertEqual(row["output_docx_path"], str(docx_path))
        self.assertEqual(messages[0].run_id, run_id)
        self.assertEqual(messages[0].docx_path, str(docx_path))


if __name__ == "__main__":
    unittest.main()
