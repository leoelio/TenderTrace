from __future__ import annotations

from dataclasses import dataclass
import hashlib
import uuid

from tendertrace.config import Settings
from tendertrace.db import connection
from tendertrace.llm.gateway import ModelCallResult


@dataclass(frozen=True)
class ModelAuditRecord:
    id: str
    run_id: str
    status: str


def record_model_audit(
    settings: Settings,
    *,
    run_id: str,
    result: ModelCallResult,
    prompt_text: str,
) -> ModelAuditRecord:
    record_id = uuid.uuid4().hex
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO model_audits(
                id, run_id, mode, provider, model, status, latency_ms, error,
                prompt_sha256, response_sha256
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                run_id,
                result.mode,
                result.provider,
                result.model,
                result.status,
                result.latency_ms,
                result.error,
                _sha256(prompt_text),
                _sha256(result.text),
            ),
        )
    return ModelAuditRecord(id=record_id, run_id=run_id, status=result.status)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
