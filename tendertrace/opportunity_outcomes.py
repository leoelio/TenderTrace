from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlsplit

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


OUTCOME_REASON_LABELS = {
    "price": "价格竞争力",
    "technical_fit": "技术匹配度",
    "relationship": "客户关系与影响力",
    "delivery": "交付与服务能力",
    "compliance": "合规与资质",
    "qualification": "资格条件",
    "partner": "伙伴协同",
    "incumbent": "既有供应商优势",
    "execution": "投标执行质量",
    "other": "其他已核实原因",
}


@dataclass(frozen=True)
class OpportunityOutcome:
    notice_id: str
    result: str
    reason_code: str
    reason_label: str
    winner_name: str
    award_amount: float | None
    currency: str
    summary: str
    lessons: str
    customer_feedback: str
    follow_up_action: str
    evidence_url: str
    evidence_text: str
    recorded_by: str
    finalized_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def record_outcome(
    settings: Settings,
    notice_id: str,
    payload: dict[str, Any],
    *,
    expected_result: str | None = None,
    actor: str = "",
) -> OpportunityOutcome:
    values = validate_outcome(payload, expected_result=expected_result)
    finalized_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    init_db(settings)
    with connection(settings) as conn:
        exists = conn.execute(
            "SELECT 1 FROM notices WHERE id = ?",
            (notice_id,),
        ).fetchone()
        if exists is None:
            raise LookupError("opportunity notice does not exist")
        conn.execute(
            """
            INSERT INTO opportunity_outcomes(
                notice_id, result, reason_code, winner_name, award_amount,
                currency, summary, lessons, customer_feedback, follow_up_action,
                evidence_url, evidence_text, recorded_by, finalized_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(notice_id) DO UPDATE SET
                result = excluded.result,
                reason_code = excluded.reason_code,
                winner_name = excluded.winner_name,
                award_amount = excluded.award_amount,
                currency = excluded.currency,
                summary = excluded.summary,
                lessons = excluded.lessons,
                customer_feedback = excluded.customer_feedback,
                follow_up_action = excluded.follow_up_action,
                evidence_url = excluded.evidence_url,
                evidence_text = excluded.evidence_text,
                recorded_by = excluded.recorded_by,
                finalized_at = excluded.finalized_at,
                updated_at = datetime('now')
            """,
            (
                notice_id,
                values["result"],
                values["reason_code"],
                values["winner_name"],
                values["award_amount"],
                values["currency"],
                values["summary"],
                values["lessons"],
                values["customer_feedback"],
                values["follow_up_action"],
                values["evidence_url"],
                values["evidence_text"],
                actor.strip(),
                finalized_at,
            ),
        )
    outcome = get_outcome(settings, notice_id)
    assert outcome is not None
    return outcome


def validate_outcome(
    payload: dict[str, Any],
    *,
    expected_result: str | None = None,
) -> dict[str, object]:
    result = _text(payload.get("result"))
    if result not in {"won", "lost"}:
        raise ValueError("outcome result must be won or lost")
    if expected_result and result != expected_result:
        raise ValueError(f"outcome result must be {expected_result} for this action")
    reason_code = _text(payload.get("reason_code"))
    if reason_code not in OUTCOME_REASON_LABELS:
        raise ValueError("outcome reason_code is not supported")
    summary = _text(payload.get("summary"))
    lessons = _text(payload.get("lessons"))
    if not summary:
        raise ValueError("outcome summary is required")
    if not lessons:
        raise ValueError("outcome lessons are required")
    evidence_url = _text(payload.get("evidence_url"))
    evidence_text = _text(payload.get("evidence_text"))
    if not evidence_url and not evidence_text:
        raise ValueError("outcome evidence_url or evidence_text is required")
    if evidence_url:
        parsed = urlsplit(evidence_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("outcome evidence_url must be an http(s) URL")
    award_amount = _amount(payload.get("award_amount"))
    currency = _text(payload.get("currency")).upper()
    if award_amount is not None and not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("outcome currency must be a three-letter code when amount is set")
    return {
        "result": result,
        "reason_code": reason_code,
        "winner_name": _text(payload.get("winner_name")),
        "award_amount": award_amount,
        "currency": currency,
        "summary": summary,
        "lessons": lessons,
        "customer_feedback": _text(payload.get("customer_feedback")),
        "follow_up_action": _text(payload.get("follow_up_action")),
        "evidence_url": evidence_url,
        "evidence_text": evidence_text,
    }


def get_outcome(settings: Settings, notice_id: str) -> OpportunityOutcome | None:
    return outcome_snapshots(settings, [notice_id]).get(notice_id)


def outcome_snapshots(
    settings: Settings,
    notice_ids: list[str],
) -> dict[str, OpportunityOutcome]:
    unique_ids = list(dict.fromkeys(value for value in notice_ids if value))
    if not unique_ids:
        return {}
    init_db(settings)
    placeholders = ",".join("?" for _ in unique_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"SELECT * FROM opportunity_outcomes WHERE notice_id IN ({placeholders})",
            unique_ids,
        ).fetchall()
    return {str(row["notice_id"]): _from_row(row) for row in rows}


def _from_row(row: Any) -> OpportunityOutcome:
    reason_code = str(row["reason_code"] or "")
    amount = row["award_amount"]
    return OpportunityOutcome(
        notice_id=str(row["notice_id"]),
        result=str(row["result"]),
        reason_code=reason_code,
        reason_label=OUTCOME_REASON_LABELS.get(reason_code, reason_code),
        winner_name=str(row["winner_name"] or ""),
        award_amount=float(amount) if amount is not None else None,
        currency=str(row["currency"] or ""),
        summary=str(row["summary"] or ""),
        lessons=str(row["lessons"] or ""),
        customer_feedback=str(row["customer_feedback"] or ""),
        follow_up_action=str(row["follow_up_action"] or ""),
        evidence_url=str(row["evidence_url"] or ""),
        evidence_text=str(row["evidence_text"] or ""),
        recorded_by=str(row["recorded_by"] or ""),
        finalized_at=str(row["finalized_at"] or ""),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def _amount(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        amount = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("outcome award_amount must be numeric") from exc
    if amount <= 0:
        raise ValueError("outcome award_amount must be greater than zero")
    return round(amount, 2)


def _text(value: object) -> str:
    return " ".join(str(value or "").split())
