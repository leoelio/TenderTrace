from __future__ import annotations

from dataclasses import asdict, dataclass

from tendertrace.config import Settings
from tendertrace.db import connection


@dataclass(frozen=True)
class DeliveryPreference:
    provider: str
    receive_id: str
    receive_id_type: str
    label: str | None
    updated_at: str

    def safe_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("receive_id", None)
        value["configured"] = True
        return value


def save_feishu_receiver(
    settings: Settings,
    *,
    receive_id: str,
    receive_id_type: str,
    label: str | None = None,
) -> DeliveryPreference:
    receive_id = receive_id.strip()
    receive_id_type = receive_id_type.strip()
    if not receive_id:
        raise ValueError("receive_id is required")
    if receive_id_type not in {"chat_id", "open_id", "union_id", "user_id", "email"}:
        raise ValueError("unsupported receive_id_type")
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO integration_preferences(provider, receive_id, receive_id_type, label)
            VALUES ('feishu', ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                receive_id = excluded.receive_id,
                receive_id_type = excluded.receive_id_type,
                label = excluded.label,
                updated_at = datetime('now')
            """,
            (receive_id, receive_id_type, (label or "").strip() or None),
        )
    preference = load_feishu_receiver(settings)
    if preference is None:
        raise RuntimeError("Feishu receiver was not persisted")
    return preference


def load_feishu_receiver(settings: Settings) -> DeliveryPreference | None:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT provider, receive_id, receive_id_type, label, updated_at
            FROM integration_preferences
            WHERE provider = 'feishu'
            """
        ).fetchone()
    if row is None:
        return None
    return DeliveryPreference(
        provider=row["provider"],
        receive_id=row["receive_id"],
        receive_id_type=row["receive_id_type"],
        label=row["label"],
        updated_at=row["updated_at"],
    )


def resolve_feishu_receiver(
    settings: Settings,
    *,
    receive_id: str | None = None,
    receive_id_type: str | None = None,
) -> tuple[str | None, str | None]:
    if receive_id:
        return receive_id, receive_id_type or settings.feishu_default_receive_id_type
    preference = load_feishu_receiver(settings)
    if preference is not None:
        return preference.receive_id, preference.receive_id_type
    return settings.feishu_default_receive_id or None, receive_id_type or settings.feishu_default_receive_id_type
