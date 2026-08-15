from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.delivery.feishu_bitable import (
    list_feishu_bitable_records,
    update_feishu_bitable_records,
)
from tendertrace.runner import persist_notices_and_clusters


PARTNER_LEAD_READY_STATES = frozenset({"伙伴提交", "待导入"})


@dataclass(frozen=True)
class FeishuLeadImportResult:
    status: str
    dry_run: bool
    run_id: str = ""
    scanned_count: int = 0
    candidate_count: int = 0
    imported_count: int = 0
    existing_count: int = 0
    skipped_count: int = 0
    updated_count: int = 0
    invalid_records: tuple[dict[str, str], ...] = ()
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FeishuLeadImportRun:
    id: str
    mode: str
    status: str
    scanned_count: int
    candidate_count: int
    imported_count: int
    existing_count: int
    skipped_count: int
    updated_count: int
    invalid_count: int
    message: str
    started_at: str
    finished_at: str
    duration_ms: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def import_partner_leads(
    settings: Settings,
    *,
    dry_run: bool = False,
    http_client_factory=httpx.Client,
) -> FeishuLeadImportResult:
    init_db(settings)
    run_id = str(uuid4())
    started_at = datetime.now().astimezone()

    def finish(result: FeishuLeadImportResult) -> FeishuLeadImportResult:
        _record_import_run(settings, result, started_at=started_at)
        return result

    try:
        records = list_feishu_bitable_records(
            settings,
            http_client_factory=http_client_factory,
        )
    except Exception as exc:
        return finish(
            FeishuLeadImportResult(
                status="failed",
                dry_run=dry_run,
                run_id=run_id,
                message=f"{type(exc).__name__}: {exc}",
            )
        )

    candidates: list[tuple[str, Notice]] = []
    invalid: list[dict[str, str]] = []
    skipped = 0
    for record in records:
        record_id = str(record.get("record_id") or "").strip()
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
        if not _is_partner_candidate(fields):
            skipped += 1
            continue
        title = _cell_text(fields.get("标题"))
        source_url = _cell_text(fields.get("来源链接"))
        if not record_id or not title or not source_url:
            invalid.append(
                {
                    "record_id": record_id,
                    "title": title,
                    "reason": "标题、来源链接和飞书 record_id 均为必填项",
                }
            )
            continue
        candidates.append((record_id, _notice_from_record(record_id, fields)))

    existing_ids = _existing_notice_ids(settings, [record_id for record_id, _ in candidates])
    new_candidates = [item for item in candidates if item[0] not in existing_ids]
    if dry_run:
        return finish(
            FeishuLeadImportResult(
                status="preview",
                dry_run=True,
                run_id=run_id,
                scanned_count=len(records),
                candidate_count=len(candidates),
                existing_count=len(existing_ids),
                skipped_count=skipped,
                invalid_records=tuple(invalid),
                message="preview completed without writing local or Feishu data",
            )
        )

    if new_candidates:
        persist_notices_and_clusters(settings, [notice for _, notice in new_candidates])
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    updates = [
        (
            record_id,
            {
                "状态": "已入库",
                "公告ID": record_id,
                "项目指纹": f"feishu_partner:{record_id}",
                "最近同步时间": now,
            },
        )
        for record_id, _ in candidates
    ]
    try:
        updated_count = update_feishu_bitable_records(
            settings,
            updates=updates,
            http_client_factory=http_client_factory,
        )
    except Exception as exc:
        return finish(
            FeishuLeadImportResult(
                status="partial" if new_candidates else "failed",
                dry_run=False,
                run_id=run_id,
                scanned_count=len(records),
                candidate_count=len(candidates),
                imported_count=len(new_candidates),
                existing_count=len(existing_ids),
                skipped_count=skipped,
                invalid_records=tuple(invalid),
                message=(
                    "local import completed but Feishu update failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        )
    return finish(
        FeishuLeadImportResult(
            status="imported",
            dry_run=False,
            run_id=run_id,
            scanned_count=len(records),
            candidate_count=len(candidates),
            imported_count=len(new_candidates),
            existing_count=len(existing_ids),
            skipped_count=skipped,
            updated_count=updated_count,
            invalid_records=tuple(invalid),
            message="partner leads are searchable in the local notice library",
        )
    )


def list_feishu_lead_import_runs(
    settings: Settings,
    *,
    limit: int = 20,
) -> list[FeishuLeadImportRun]:
    init_db(settings)
    safe_limit = min(max(int(limit), 1), 100)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM feishu_lead_import_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [FeishuLeadImportRun(**dict(row)) for row in rows]


def _record_import_run(
    settings: Settings,
    result: FeishuLeadImportResult,
    *,
    started_at: datetime,
) -> None:
    finished_at = datetime.now().astimezone()
    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO feishu_lead_import_runs(
                id, mode, status, scanned_count, candidate_count, imported_count,
                existing_count, skipped_count, updated_count, invalid_count,
                message, started_at, finished_at, duration_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                "preview" if result.dry_run else "import",
                result.status,
                result.scanned_count,
                result.candidate_count,
                result.imported_count,
                result.existing_count,
                result.skipped_count,
                result.updated_count,
                len(result.invalid_records),
                result.message,
                started_at.isoformat(timespec="milliseconds"),
                finished_at.isoformat(timespec="milliseconds"),
                duration_ms,
            ),
        )


def _is_partner_candidate(fields: dict[str, Any]) -> bool:
    if _cell_text(fields.get("公告ID")) or _cell_text(fields.get("项目指纹")):
        return False
    return _cell_text(fields.get("状态")) in PARTNER_LEAD_READY_STATES


def _notice_from_record(record_id: str, fields: dict[str, Any]) -> Notice:
    source_url = _cell_text(fields.get("来源链接"))
    content = _cell_text(fields.get("线索正文"))
    attachment_urls = [
        value.strip()
        for value in _cell_text(fields.get("附件链接")).splitlines()
        if value.strip()
    ]
    submitter = _cell_text(fields.get("伙伴提交人"))
    origin = _cell_text(fields.get("来源")) or "飞书合作伙伴"
    return Notice(
        id=record_id,
        source_site="feishu_partner",
        title=_cell_text(fields.get("标题")),
        publish_time=_cell_text(fields.get("发布时间"))[:10],
        region=_cell_text(fields.get("地区")),
        purchaser=_cell_text(fields.get("采购人")),
        source_url=source_url,
        content_text=content,
        core_content=(content or _cell_text(fields.get("标题")))[:600],
        attachments=[
            Attachment(name=f"伙伴附件 {index}", url=url)
            for index, url in enumerate(attachment_urls, start=1)
        ],
        fields={
            "cluster_key": f"feishu_partner:{record_id}",
            "source_origin": origin,
            "submitted_by": submitter,
            "feishu_record_id": record_id,
            "evidence": {
                "source_url": source_url,
                "excerpt": (content or _cell_text(fields.get("标题")))[:500],
                "attachments": attachment_urls,
                "fact_checks": ["partner_submitted_pending_source_verification"],
                "quality_score": 0.55,
            },
        },
    )


def _existing_notice_ids(settings: Settings, record_ids: list[str]) -> set[str]:
    if not record_ids:
        return set()
    notice_ids = [f"feishu_partner:{record_id}" for record_id in record_ids]
    placeholders = ",".join("?" for _ in notice_ids)
    with connection(settings) as conn:
        rows = conn.execute(
            f"SELECT id FROM notices WHERE id IN ({placeholders})",
            notice_ids,
        ).fetchall()
    return {str(row["id"]).split(":", 1)[-1] for row in rows}


def _cell_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (_cell_text(item) for item in value))).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("link") or "").strip()
    return str(value or "").strip()
