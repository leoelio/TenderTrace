from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.delivery.feishu_report import deliver_report_to_feishu
from tendertrace.delivery.ledger import list_delivery_attempts
from tendertrace.integrations.feishu import FeishuError


class _SuccessfulClient:
    def send_file(self, path, **_kwargs):
        return {"code": 0, "data": {"message_id": f"sent-{Path(path).stem}"}}


class _FailedClient:
    def send_file(self, _path, **_kwargs):
        raise FeishuError("app unavailable")


class FeishuReportDeliveryTests(unittest.TestCase):
    def test_success_and_failure_are_recorded_without_recipient_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            report = root / "outbox" / "report.docx"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_bytes(b"docx")

            sent = deliver_report_to_feishu(
                settings,
                docx_path=report,
                run_id="run-1",
                receive_id="oc-secret-target",
                client=_SuccessfulClient(),
            )
            failed = deliver_report_to_feishu(
                settings,
                docx_path=report,
                run_id="run-2",
                receive_id="oc-secret-target",
                client=_FailedClient(),
            )
            attempts = list_delivery_attempts(settings, channel="feishu")

        self.assertEqual(sent.status, "sent")
        self.assertEqual(failed.status, "failed")
        self.assertEqual([item.status for item in attempts], ["failed", "sent"])
        self.assertNotIn("oc-secret-target", str([item.to_dict() for item in attempts]))


if __name__ == "__main__":
    unittest.main()
