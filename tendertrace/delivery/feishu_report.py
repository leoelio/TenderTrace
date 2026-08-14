from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tendertrace.config import Settings
from tendertrace.delivery.ledger import record_delivery_attempt
from tendertrace.delivery.preferences import resolve_feishu_receiver
from tendertrace.integrations.feishu import FeishuClient, FeishuError


@dataclass(frozen=True)
class FeishuReportDelivery:
    status: str
    file_name: str
    attempt_id: str
    message_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def deliver_report_to_feishu(
    settings: Settings,
    *,
    docx_path: Path | str,
    run_id: str | None = None,
    subscription_id: str | None = None,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
    client: FeishuClient | None = None,
) -> FeishuReportDelivery:
    path = Path(docx_path)
    receive_id, receive_id_type = resolve_feishu_receiver(
        settings,
        receive_id=receive_id,
        receive_id_type=receive_id_type,
    )
    try:
        payload = (client or FeishuClient(settings)).send_file(
            path,
            receive_id=receive_id,
            receive_id_type=receive_id_type,
        )
        data = payload.get("data")
        message_id = str(data.get("message_id") or "") if isinstance(data, dict) else ""
        attempt = record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="report",
            artifact_key=path.name,
            run_id=run_id,
            subscription_id=subscription_id,
            status="sent",
            external_id=message_id or None,
        )
        return FeishuReportDelivery(
            status="sent",
            file_name=path.name,
            attempt_id=attempt.id,
            message_id=message_id or None,
        )
    except (FeishuError, OSError) as exc:
        attempt = record_delivery_attempt(
            settings,
            channel="feishu",
            artifact_type="report",
            artifact_key=path.name,
            run_id=run_id,
            subscription_id=subscription_id,
            status="failed",
            error=str(exc),
        )
        return FeishuReportDelivery(
            status="failed",
            file_name=path.name,
            attempt_id=attempt.id,
            error=str(exc),
        )
