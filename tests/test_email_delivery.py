from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.delivery.emailer import send_report_email


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message) -> object:
        self.messages.append(message)
        return {}


class EmailDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeSMTP.instances = []

    def test_send_report_email_skips_when_channel_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))
            docx = Path(tmp) / "report.docx"
            docx.write_bytes(b"docx")

            result = send_report_email(
                settings,
                docx_path=docx,
                query="query",
                run_id="run-1",
                notice_count=1,
                smtp_factory=FakeSMTP,
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(FakeSMTP.instances, [])

    def test_send_report_email_sends_docx_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "TENDERTRACE_DELIVERY_CHANNELS=web,outbox,email\n"
                "TENDERTRACE_SMTP_HOST=smtp.example.com\n"
                "TENDERTRACE_SMTP_PORT=2525\n"
                "TENDERTRACE_SMTP_USERNAME=sender\n"
                "TENDERTRACE_SMTP_PASSWORD=secret-mail-password\n"
                "TENDERTRACE_SMTP_FROM=sender@example.com\n"
                "TENDERTRACE_SMTP_TO=a@example.com,b@example.com\n",
                encoding="utf-8",
            )
            settings = Settings.load(root)
            docx = root / "report.docx"
            docx.write_bytes(b"docx")

            result = send_report_email(
                settings,
                docx_path=docx,
                query="最近1个月上海服务器招标信息",
                run_id="run-1",
                notice_count=3,
                smtp_factory=FakeSMTP,
            )

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.recipient_count, 2)
        smtp = FakeSMTP.instances[0]
        self.assertEqual((smtp.host, smtp.port), ("smtp.example.com", 2525))
        self.assertTrue(smtp.started_tls)
        self.assertEqual(smtp.login_args, ("sender", "secret-mail-password"))
        self.assertEqual(len(smtp.messages), 1)
        message = smtp.messages[0]
        self.assertEqual(message["From"], "sender@example.com")
        self.assertEqual(message["To"], "a@example.com, b@example.com")
        self.assertIn("TenderTrace 报告", message["Subject"])
        self.assertTrue(any(part.get_filename() == "report.docx" for part in message.walk()))


if __name__ == "__main__":
    unittest.main()
