from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.delivery.feishu_report import build_report_digest_card, deliver_report_to_feishu
from tendertrace.delivery.ledger import list_delivery_attempts
from tendertrace.integrations.feishu import FeishuError


class _SuccessfulClient:
    def __init__(self) -> None:
        self.cards = []

    def send_file(self, path, **_kwargs):
        return {"code": 0, "data": {"message_id": f"sent-{Path(path).stem}"}}

    def send_card(self, card, **_kwargs):
        self.cards.append(card)
        return {"code": 0, "data": {"message_id": "digest-1"}}


class _DigestFailedClient(_SuccessfulClient):
    def send_card(self, _card, **_kwargs):
        raise FeishuError("digest unavailable")


class _FailedClient:
    def send_file(self, _path, **_kwargs):
        raise FeishuError("app unavailable")


class FeishuReportDeliveryTests(unittest.TestCase):
    def test_file_and_readable_digest_are_recorded_without_recipient_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            report = root / "outbox" / "report.docx"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_bytes(b"docx")

            client = _SuccessfulClient()
            sent = deliver_report_to_feishu(
                settings,
                docx_path=report,
                run_id="run-1",
                receive_id="oc-secret-target",
                report_summary={
                    "query": "最近一个月上海服务器招标",
                    "notice_count": 3,
                    "evidence_passed": 2,
                    "source_sites": ["ccgp", "ggzy"],
                    "highlights": [{"title": "服务器采购项目", "source": "ccgp", "published": "2026-09-01"}],
                },
                client=client,
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
        self.assertEqual(sent.digest_status, "sent")
        self.assertEqual(failed.status, "failed")
        self.assertEqual(
            [(item.artifact_type, item.status) for item in attempts],
            [("report", "failed"), ("report_digest", "sent"), ("report", "sent")],
        )
        self.assertIn("最近一个月上海服务器招标", str(client.cards[0]))
        self.assertIn("服务器采购项目", str(client.cards[0]))
        self.assertNotIn("oc-secret-target", str([item.to_dict() for item in attempts]))

    def test_digest_failure_does_not_mask_a_sent_word_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings.load(root)
            init_db(settings)
            report = root / "outbox" / "report.docx"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_bytes(b"docx")

            result = deliver_report_to_feishu(
                settings,
                docx_path=report,
                receive_id="oc-secret-target",
                client=_DigestFailedClient(),
            )
            attempts = list_delivery_attempts(settings, channel="feishu")

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.digest_status, "failed")
        self.assertEqual(
            [(item.artifact_type, item.status) for item in attempts],
            [("report_digest", "failed"), ("report", "sent")],
        )

    def test_digest_card_is_readable_without_runtime_only_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            card = build_report_digest_card(
                settings,
                file_name="report.docx",
                report_summary={"query": "服务器", "notice_count": "invalid"},
            )

        self.assertEqual(card["header"]["title"]["content"], "TenderTrace 招投标检索简报")
        self.assertIn("服务器", str(card))
        self.assertIn("结果**：0 条", str(card))


if __name__ == "__main__":
    unittest.main()
