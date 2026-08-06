from __future__ import annotations

from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path
import smtplib
from typing import Protocol

from tendertrace.config import Settings


class SMTPClient(Protocol):
    def __enter__(self) -> "SMTPClient": ...

    def __exit__(self, exc_type, exc, tb) -> None: ...

    def starttls(self) -> None: ...

    def login(self, username: str, password: str) -> None: ...

    def send_message(self, message: EmailMessage) -> object: ...


@dataclass(frozen=True)
class EmailDeliveryResult:
    status: str
    channel: str = "email"
    recipient_count: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def send_report_email(
    settings: Settings,
    *,
    docx_path: Path,
    query: str,
    run_id: str,
    notice_count: int,
    smtp_factory=smtplib.SMTP,
) -> EmailDeliveryResult:
    if "email" not in settings.delivery_channels:
        return EmailDeliveryResult(status="skipped", message="email channel is disabled")
    missing = _missing_settings(settings)
    if missing:
        return EmailDeliveryResult(
            status="skipped",
            message=f"missing SMTP settings: {', '.join(missing)}",
        )
    try:
        message = _build_message(
            settings,
            docx_path=docx_path,
            query=query,
            run_id=run_id,
            notice_count=notice_count,
        )
        with smtp_factory(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout,
        ) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            password = settings.smtp_password()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, password)
            smtp.send_message(message)
    except Exception as exc:
        return EmailDeliveryResult(status="failed", message=f"{type(exc).__name__}: {exc}")
    return EmailDeliveryResult(status="sent", recipient_count=len(settings.smtp_to))


def _missing_settings(settings: Settings) -> list[str]:
    missing: list[str] = []
    if not settings.smtp_host:
        missing.append("TENDERTRACE_SMTP_HOST")
    if not settings.smtp_from:
        missing.append("TENDERTRACE_SMTP_FROM")
    if not settings.smtp_to:
        missing.append("TENDERTRACE_SMTP_TO")
    if settings.smtp_username and not settings.smtp_password_present:
        missing.append("TENDERTRACE_SMTP_PASSWORD")
    return missing


def _build_message(
    settings: Settings,
    *,
    docx_path: Path,
    query: str,
    run_id: str,
    notice_count: int,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"TenderTrace 报告：{query[:60]}"
    message["From"] = settings.smtp_from
    message["To"] = ", ".join(settings.smtp_to)
    message.set_content(
        "\n".join(
            [
                "TenderTrace 本轮招投标信息聚合已完成。",
                f"问题：{query}",
                f"Run ID：{run_id}",
                f"新增/保留公告数：{notice_count}",
                "Word 报告见附件。",
            ]
        )
    )
    data = docx_path.read_bytes()
    message.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=docx_path.name,
    )
    return message
