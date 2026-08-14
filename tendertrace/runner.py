from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import hashlib
from pathlib import Path
import shutil
from typing import Any
from typing import Protocol

from tendertrace.adapters.ccgp import Attachment, Notice
from tendertrace.adapters.multi import MultiSourceAdapter
from tendertrace.config import ModelMode, Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.delivery.emailer import send_report_email
from tendertrace.delivery.feishu_bitable import sync_notices_to_bitable
from tendertrace.delivery.feishu_report import deliver_report_to_feishu
from tendertrace.intent import compile_intent
from tendertrace.llm.enhancer import enhance_bidql_with_model
from tendertrace.llm.gateway import ModelGateway
from tendertrace.opportunity import enrich_opportunity_intelligence
from tendertrace.pipeline.attachments import Downloader, enrich_attachment_snapshots
from tendertrace.pipeline.dedup import clean_and_cluster_notices
from tendertrace.pipeline.evidence import attach_evidence
from tendertrace.pipeline.fields import extract_structured_fields
from tendertrace.retrieval import search_notices, upsert_notice_fts
from tendertrace.report.docx_writer import write_report
from tendertrace.runlog import finish_run, register_outbox_message, start_run
from tendertrace.runtime.bus import EventBus
from tendertrace.runtime.checkpoint import SqliteCheckpointer
from tendertrace.runtime.graph import TenderGraph
from tendertrace.runtime.state import RunState
from tendertrace.runtime.trace import SqliteTraceStore
from tendertrace.scheduling.ledger import mark_sent, unsent_cluster_keys


class NoticeAdapter(Protocol):
    def collect(
        self,
        bidql: dict[str, object],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]: ...


@dataclass(frozen=True)
class RunOnceResult:
    run_id: str
    status: str
    notice_count: int
    docx_path: str | None
    outbox_path: str | None
    trace_events: int
    stats: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_once(
    *,
    settings: Settings,
    query: str,
    now: datetime | None = None,
    max_pages: int = 1,
    max_results: int = 10,
    adapter: NoticeAdapter | None = None,
    subscription_id: str | None = None,
    incremental: bool = False,
    attachment_downloader: Downloader | None = None,
    model_gateway: ModelGateway | None = None,
    model_strategy: str | None = None,
    delivery_channels: tuple[str, ...] | list[str] | None = None,
    run_id: str | None = None,
) -> RunOnceResult:
    init_db(settings)
    run_at = now or datetime.now().astimezone()
    initial_state = RunState.new(query, run_id=run_id)
    bidql = compile_intent(query, now=run_at)
    window = bidql.get("time", {}).get("resolved_window", {})

    bus = EventBus()
    trace_store = SqliteTraceStore(settings)
    bus.subscribe(trace_store.record)
    checkpointer = SqliteCheckpointer(settings)
    source_adapter = adapter or MultiSourceAdapter.default(settings)

    def intent(state: RunState, context) -> RunState:
        context.emit_tool_call("intent.rule_parser", {"query_length": len(state.original_query)})
        strategy = _normalize_model_strategy(model_strategy)
        enhancement = enhance_bidql_with_model(
            _settings_for_model_strategy(settings, strategy),
            bidql,
            run_id=state.run_id,
            gateway=model_gateway,
        )
        context.emit_tool_call(
            "llm.intent_enhancer",
            {
                "strategy": strategy,
                **enhancement.result.safe_dict(),
                "applied_keywords": enhancement.applied_keywords,
                "applied_negatives": enhancement.applied_negatives,
            },
        )
        return state.with_updates(
            intent=enhancement.bidql,
            quality={**state.quality, "model": enhancement.result.safe_dict()},
        )

    def collect(state: RunState, context) -> RunState:
        local_result = search_notices(settings, state.intent, max_results=max_results)
        local_notices = local_result.notices
        pre_skipped_keys: set[str] = set()
        if subscription_id and incremental:
            local_notices, pre_skipped_keys = _filter_unsent_candidates(
                settings,
                subscription_id=subscription_id,
                notices=local_notices,
            )
        source_stats = [local_result.stats]
        if _can_use_local_only(local_notices, max_results, source_adapter):
            dedup_result = clean_and_cluster_notices(local_notices[:max_results])
            notices = dedup_result.notices
            region_scope = _region_scope_summary(state.intent, source_stats)
            context.emit_tool_call(
                "retrieval.local_fts",
                {
                    "count": len(local_notices),
                    "engine": local_result.stats.get("engine"),
                    "cache_hit": True,
                    "source_sites": _source_sites(local_notices),
                },
            )
            context.emit_tool_call("pipeline.clean_dedup", dedup_result.stats)
            return state.with_updates(
                intent=_with_region_scope(state.intent, region_scope),
                notices=[notice.to_dict() for notice in notices],
                funnel={
                    "collected": len(local_notices),
                    "local_retrieved": len(local_notices),
                    "source_collected": 0,
                    "deduped": len(notices),
                    "source_sites": _source_sites(notices),
                    "source_stats": source_stats,
                    "region_scope": region_scope,
                    "retrieval_engine": local_result.stats.get("engine"),
                    "pre_skipped_sent": len(pre_skipped_keys),
                    **dedup_result.stats,
                },
            )

        context.emit_tool_call(
            f"adapter.{getattr(source_adapter, 'name', 'custom')}.collect",
            {
                "max_pages": max_pages,
                "max_results": max_results,
                "local_retrieved": len(local_notices),
                "local_source_sites": _source_sites(local_notices),
            },
        )
        collected = source_adapter.collect(
            state.intent,
            max_pages=max_pages,
            max_results=max_results,
        )
        source_stats.extend(
            item.to_dict() if hasattr(item, "to_dict") else item
            for item in getattr(source_adapter, "last_source_stats", [])
        )
        notices = [*local_notices, *collected]
        pre_skipped_keys_after_collect: set[str] = set()
        if subscription_id and incremental:
            notices, pre_skipped_keys_after_collect = _filter_unsent_candidates(
                settings,
                subscription_id=subscription_id,
                notices=notices,
            )
            pre_skipped_keys |= pre_skipped_keys_after_collect
        region_scope = _region_scope_summary(state.intent, source_stats)
        collected_count = len(local_result.notices) + len(collected)
        dedup_result = clean_and_cluster_notices(notices)
        notices = dedup_result.notices
        context.emit_tool_call("pipeline.clean_dedup", dedup_result.stats)
        return state.with_updates(
            intent=_with_region_scope(state.intent, region_scope),
            notices=[notice.to_dict() for notice in notices],
            funnel={
                "collected": collected_count,
                "local_retrieved": len(local_notices),
                "source_collected": len(collected),
                "deduped": len(notices),
                "source_sites": _source_sites(notices),
                "source_stats": source_stats,
                "region_scope": region_scope,
                "retrieval_engine": local_result.stats.get("engine"),
                "pre_skipped_sent": len(pre_skipped_keys),
                **dedup_result.stats,
            },
        )

    def evidence(state: RunState, context) -> RunState:
        notices = [_notice_from_dict(item) for item in state.notices]
        attachment_result = enrich_attachment_snapshots(
            notices,
            settings=settings,
            max_per_notice=settings.attachment_max_per_notice,
            max_bytes=settings.attachment_max_bytes,
            downloader=attachment_downloader,
        )
        notices = attachment_result.notices
        context.emit_tool_call("pipeline.attachment_extract", attachment_result.stats)
        structured_result = extract_structured_fields(notices)
        notices = structured_result.notices
        context.emit_tool_call("pipeline.structured_fields", structured_result.stats)
        evidence_result = attach_evidence(notices)
        notices = evidence_result.notices
        opportunity_result = enrich_opportunity_intelligence(notices, as_of=run_at)
        notices = opportunity_result.notices
        deduped_count = len(notices)
        _persist_notices_and_clusters(settings, notices)
        context.emit_tool_call("pipeline.evidence_validate", evidence_result.stats)
        context.emit_tool_call("pipeline.opportunity_intelligence", opportunity_result.stats)
        if subscription_id and incremental:
            cluster_keys = [_cluster_key(notice.to_dict()) for notice in notices]
            with connection(settings) as conn:
                unsent = set(
                    unsent_cluster_keys(
                        conn,
                        subscription_id=subscription_id,
                        cluster_keys=cluster_keys,
                    )
                )
            notices = [notice for notice in notices if _cluster_key(notice.to_dict()) in unsent]
        pre_skipped_sent = int(state.funnel.get("pre_skipped_sent") or 0)
        skipped_sent = (
            pre_skipped_sent + deduped_count - len(notices)
            if subscription_id and incremental
            else 0
        )
        return state.with_updates(
            notices=[notice.to_dict() for notice in notices],
            funnel={
                **state.funnel,
                "new": len(notices),
                "skipped_sent": skipped_sent,
                "source_sites": _source_sites(notices),
                **attachment_result.stats,
                **structured_result.stats,
                **evidence_result.stats,
                **opportunity_result.stats,
            },
            quality={
                "attachments": attachment_result.stats,
                "structured_fields": structured_result.stats,
                "evidence": evidence_result.stats,
                "opportunity": opportunity_result.stats,
            },
        )

    def report(state: RunState, context) -> RunState:
        context.emit_tool_call("report.docx_writer", {"notice_count": len(state.notices)})
        report_path = write_report(
            query=state.original_query,
            bidql=state.intent,
            notices=state.notices,
            output_dir=settings.outputs_dir,
            generated_at=run_at,
            run_mode="incremental" if incremental else "full",
            run_stats=state.funnel,
        )
        settings.outbox_dir.mkdir(parents=True, exist_ok=True)
        outbox_path = settings.outbox_dir / report_path.name
        shutil.copy2(report_path, outbox_path)
        register_outbox_message(
            settings,
            run_id=state.run_id,
            docx_path=outbox_path,
            subscription_id=subscription_id,
        )
        email_result = send_report_email(
            settings,
            docx_path=outbox_path,
            query=state.original_query,
            run_id=state.run_id,
            notice_count=len(state.notices),
        )
        context.emit_tool_call("delivery.email", email_result.to_dict())
        feishu_result = sync_notices_to_bitable(
            settings,
            notices=state.notices,
            bidql=state.intent,
            query=state.original_query,
            run_id=state.run_id,
            outbox_path=outbox_path,
            synced_at=run_at,
        )
        context.emit_tool_call("delivery.feishu_bitable", feishu_result.to_dict())
        selected_channels = {
            str(channel).strip().lower()
            for channel in (delivery_channels or settings.delivery_channels)
        }
        if selected_channels.intersection({"feishu", "feishu_message"}):
            feishu_message_result = deliver_report_to_feishu(
                settings,
                docx_path=outbox_path,
                run_id=state.run_id,
                subscription_id=subscription_id,
            ).to_dict()
        else:
            feishu_message_result = {
                "status": "skipped",
                "file_name": outbox_path.name,
                "reason": "feishu channel not selected",
            }
        context.emit_tool_call("delivery.feishu_message", feishu_message_result)
        if subscription_id and incremental:
            with connection(settings) as conn:
                for notice in state.notices:
                    mark_sent(
                        conn,
                        subscription_id=subscription_id,
                        cluster_key=_cluster_key(notice),
                        run_id=state.run_id,
                        docx_path=str(outbox_path),
                    )
        return state.with_updates(
            artifacts={"docx_path": str(report_path), "outbox_path": str(outbox_path)},
            funnel={
                **state.funnel,
                "email_delivery": email_result.to_dict(),
                "feishu_bitable_delivery": feishu_result.to_dict(),
                "feishu_message_delivery": feishu_message_result,
            },
        )

    graph = (
        TenderGraph()
        .add_node("intent", intent)
        .add_node("collect", collect)
        .add_node("evidence", evidence)
        .add_node("report", report)
        .add_edge("intent", "collect")
        .add_edge("collect", "evidence")
        .add_edge("evidence", "report")
    )

    start_run(
        settings,
        run_id=initial_state.run_id,
        subscription_id=subscription_id,
        original_query=query,
        mode="incremental" if incremental else "full",
        window_start=window.get("from"),
        window_end=window.get("to"),
    )
    try:
        final_state = graph.run(initial_state, checkpointer=checkpointer, event_bus=bus)
    except Exception as exc:
        finish_run(
            settings,
            run_id=initial_state.run_id,
            status="failed",
            output_docx_path=None,
            stats={"trace_events": len(trace_store.list_events(initial_state.run_id))},
            error=str(exc),
        )
        raise

    trace_events = len(trace_store.list_events(final_state.run_id))
    final_stats = {
        "notice_count": len(final_state.notices),
        "trace_events": trace_events,
        **final_state.funnel,
    }
    finish_run(
        settings,
        run_id=final_state.run_id,
        status=final_state.status,
        output_docx_path=final_state.artifacts.get("docx_path"),
        stats=final_stats,
    )
    return RunOnceResult(
        run_id=final_state.run_id,
        status=final_state.status,
        notice_count=len(final_state.notices),
        docx_path=_string_or_none(final_state.artifacts.get("docx_path")),
        outbox_path=_string_or_none(final_state.artifacts.get("outbox_path")),
        trace_events=trace_events,
        stats=final_stats,
    )


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _normalize_model_strategy(value: str | None) -> str:
    strategy = (value or "config").strip().lower()
    aliases = {
        "default": "config",
        "auto": "config",
        "rules_only": "rules",
        "local_rules": "rules",
        "local_model": "local",
        "cloud_model": "cloud",
        "rules_cloud": "hybrid",
        "rules+cloud": "hybrid",
    }
    strategy = aliases.get(strategy, strategy)
    if strategy not in {"config", "rules", "local", "cloud", "hybrid"}:
        raise ValueError("model_strategy must be one of: config, rules, local, cloud, hybrid")
    return strategy


def _settings_for_model_strategy(settings: Settings, strategy: str) -> Settings:
    if strategy == "config":
        return settings
    if strategy == "rules":
        return replace(settings, model_enhancement_enabled=False)
    if strategy == "local":
        return replace(settings, model_mode=ModelMode.LOCAL, model_enhancement_enabled=True)
    if strategy in {"cloud", "hybrid"}:
        return replace(settings, model_mode=ModelMode.CLOUD, model_enhancement_enabled=True)
    return settings


def _can_use_local_only(
    local_notices: list[Notice],
    max_results: int,
    source_adapter: NoticeAdapter,
) -> bool:
    if len(local_notices) < max_results:
        return False
    if isinstance(source_adapter, MultiSourceAdapter):
        return len(_source_sites(local_notices)) >= 2
    return True


def _region_scope_summary(
    bidql: dict[str, Any],
    source_stats: list[dict[str, object]],
) -> dict[str, object]:
    region = bidql.get("region")
    if not isinstance(region, dict):
        return {}
    city = str(region.get("city") or "").strip()
    province = str(region.get("province") or "").strip()
    if not city or not province:
        return {}
    relaxed_sources = [
        str(item.get("source"))
        for item in source_stats
        if isinstance(item, dict) and item.get("relaxed_city") and item.get("source")
    ]
    if not relaxed_sources:
        return {
            "status": "exact_city",
            "requested_city": city,
            "requested_province": province,
        }
    message = (
        f"{city}城市级检索未命中样本，已扩大到{province}省内检索；"
        f"结果可能包含省内周边城市，请以来源链接为准。"
    )
    return {
        "status": "relaxed_city",
        "requested_city": city,
        "requested_province": province,
        "fallback_region": province,
        "relaxed_sources": relaxed_sources,
        "message": message,
    }


def _with_region_scope(
    bidql: dict[str, Any],
    region_scope: dict[str, object],
) -> dict[str, Any]:
    if not region_scope:
        return bidql
    updated = deepcopy(bidql)
    meta = updated.setdefault("meta", {})
    if isinstance(meta, dict):
        meta["region_scope"] = region_scope
    return updated


def _filter_unsent_candidates(
    settings: Settings,
    *,
    subscription_id: str,
    notices: list[Notice],
) -> tuple[list[Notice], set[str]]:
    cluster_keys = [_cluster_key(notice.to_dict()) for notice in notices]
    with connection(settings) as conn:
        unsent = set(
            unsent_cluster_keys(
                conn,
                subscription_id=subscription_id,
                cluster_keys=cluster_keys,
            )
        )
    skipped = {key for key in cluster_keys if key not in unsent}
    return [notice for notice in notices if _cluster_key(notice.to_dict()) in unsent], skipped


def _cluster_key(notice: dict[str, object]) -> str:
    fields = notice.get("fields")
    if isinstance(fields, dict) and fields.get("cluster_key"):
        return str(fields["cluster_key"])
    source_site = str(notice.get("source_site") or "")
    notice_id = str(notice.get("id") or "")
    if source_site and notice_id:
        return f"{source_site}:{notice_id}"
    return str(notice.get("source_url") or notice_id)


def _notice_from_dict(value: dict[str, Any]) -> Notice:
    return Notice(
        id=str(value["id"]),
        source_site=str(value["source_site"]),
        title=str(value["title"]),
        publish_time=str(value["publish_time"]),
        region=str(value["region"]),
        purchaser=str(value.get("purchaser") or ""),
        source_url=str(value["source_url"]),
        content_text=str(value.get("content_text") or ""),
        core_content=str(value.get("core_content") or ""),
        attachments=[
            Attachment(
                name=str(item.get("name") or ""),
                url=str(item.get("url") or ""),
            )
            for item in value.get("attachments", [])
            if isinstance(item, dict)
        ],
        fields=value.get("fields", {}) if isinstance(value.get("fields"), dict) else {},
    )


def persist_notices_and_clusters(settings: Settings, notices: list[Notice]) -> None:
    _persist_notices_and_clusters(settings, notices)


def _persist_notices_and_clusters(settings: Settings, notices: list[Notice]) -> None:
    with connection(settings) as conn:
        for notice in notices:
            fields = notice.fields
            notice_pk = f"{notice.source_site}:{notice.id}"
            cluster_key = str(fields.get("cluster_key") or notice_pk)
            conn.execute(
                """
                INSERT OR REPLACE INTO notices(
                    id, source_site, source_url, canonical_url, title, publish_time,
                    region, purchaser, content_text, core_content, attachments_json,
                    fields_json, snapshot_sha256, simhash64
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notice_pk,
                    notice.source_site,
                    notice.source_url,
                    str(fields.get("canonical_url") or notice.source_url),
                    notice.title,
                    notice.publish_time,
                    notice.region,
                    notice.purchaser,
                    notice.content_text,
                    notice.core_content,
                    json_dumps([attachment.__dict__ for attachment in notice.attachments]),
                    json_dumps(fields),
                    str(fields.get("snapshot_sha256") or ""),
                    str(fields.get("simhash64") or ""),
                ),
            )
            upsert_notice_fts(
                conn,
                notice_id=notice_pk,
                title=notice.title,
                content_text=notice.content_text,
                core_content=notice.core_content,
            )
            conn.execute(
                """
                INSERT INTO clusters(
                    cluster_key, primary_notice_id, project_no, title_norm, publish_time,
                    related_sources_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(cluster_key) DO UPDATE SET
                    primary_notice_id = excluded.primary_notice_id,
                    project_no = excluded.project_no,
                    title_norm = excluded.title_norm,
                    publish_time = excluded.publish_time,
                    related_sources_json = excluded.related_sources_json,
                    updated_at = datetime('now')
                """,
                (
                    cluster_key,
                    notice_pk,
                    str(fields.get("project_no") or ""),
                    str(fields.get("title_norm") or ""),
                    notice.publish_time,
                    json_dumps(fields.get("related_sources") or []),
                ),
            )
            evidence = fields.get("evidence")
            if isinstance(evidence, dict):
                _persist_evidence_item(
                    conn=conn,
                    notice_pk=notice_pk,
                    cluster_key=cluster_key,
                    source_site=notice.source_site,
                    evidence=evidence,
                )
            for attachment in _attachment_snapshot_records(fields):
                _persist_attachment_snapshot(
                    conn=conn,
                    notice_pk=notice_pk,
                    cluster_key=cluster_key,
                    attachment=attachment,
                )
            page_artifact = fields.get("page_artifact")
            if isinstance(page_artifact, dict):
                _persist_page_artifact(
                    conn=conn,
                    notice_pk=notice_pk,
                    cluster_key=cluster_key,
                    source_site=notice.source_site,
                    artifact=page_artifact,
                )


def _persist_evidence_item(
    *,
    conn,
    notice_pk: str,
    cluster_key: str,
    source_site: str,
    evidence: dict[str, Any],
) -> None:
    source_url = str(evidence.get("source_url") or "")
    snapshot = str(evidence.get("snapshot_sha256") or "")
    evidence_id = hashlib.sha1(
        f"{notice_pk}:{cluster_key}:{source_url}:{snapshot}".encode("utf-8")
    ).hexdigest()[:24]
    conn.execute(
        """
        INSERT OR REPLACE INTO evidence_items(
            id, notice_id, cluster_key, source_site, source_url, snapshot_sha256,
            excerpt, attachments_json, fact_checks_json, quality_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence_id,
            notice_pk,
            cluster_key,
            source_site,
            source_url,
            snapshot,
            str(evidence.get("excerpt") or ""),
            json_dumps(evidence.get("attachments") or []),
            json_dumps(evidence.get("fact_checks") or []),
            float(evidence.get("quality_score") or 0),
        ),
    )


def _attachment_snapshot_records(fields: dict[str, Any]) -> list[dict[str, Any]]:
    records = fields.get("attachment_snapshots")
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _persist_attachment_snapshot(
    *,
    conn,
    notice_pk: str,
    cluster_key: str,
    attachment: dict[str, Any],
) -> None:
    canonical = str(attachment.get("canonical_url") or attachment.get("url") or "")
    attachment_id = hashlib.sha1(
        f"{notice_pk}:{cluster_key}:{canonical}".encode("utf-8")
    ).hexdigest()[:24]
    conn.execute(
        """
        INSERT OR REPLACE INTO attachment_snapshots(
            id, notice_id, cluster_key, name, url, type, status, local_path, sha256,
            bytes, text_excerpt, text_length, error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attachment_id,
            notice_pk,
            cluster_key,
            str(attachment.get("name") or ""),
            str(attachment.get("url") or ""),
            str(attachment.get("type") or ""),
            str(attachment.get("status") or ""),
            str(attachment.get("path") or ""),
            str(attachment.get("sha256") or ""),
            int(attachment.get("bytes") or 0),
            str(attachment.get("text_excerpt") or ""),
            int(attachment.get("text_length") or 0),
            str(attachment.get("error") or ""),
        ),
    )


def _persist_page_artifact(
    *,
    conn,
    notice_pk: str,
    cluster_key: str,
    source_site: str,
    artifact: dict[str, Any],
) -> None:
    source_url = str(artifact.get("source_url") or "")
    final_url = str(artifact.get("final_url") or source_url)
    content_sha256 = str(artifact.get("content_sha256") or "")
    artifact_id = hashlib.sha1(
        f"{notice_pk}:{cluster_key}:{source_url}:{final_url}:{content_sha256}".encode("utf-8")
    ).hexdigest()[:24]
    conn.execute(
        """
        INSERT OR REPLACE INTO page_artifacts(
            id, notice_id, cluster_key, source_site, source_url, final_url, status_code,
            fetcher, content_sha256, content_length, text_excerpt, blocked, error,
            fetched_at, elapsed_ms
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact_id,
            notice_pk,
            cluster_key,
            source_site,
            source_url,
            final_url,
            int(artifact.get("status_code") or 0),
            str(artifact.get("fetcher") or ""),
            content_sha256,
            int(artifact.get("content_length") or 0),
            str(artifact.get("text_excerpt") or ""),
            1 if artifact.get("blocked") else 0,
            str(artifact.get("error") or ""),
            str(artifact.get("fetched_at") or ""),
            int(artifact.get("elapsed_ms") or 0),
        ),
    )


def _source_sites(notices: list[Notice]) -> list[str]:
    sites: set[str] = set()
    for notice in notices:
        value = notice.fields.get("source_sites")
        if isinstance(value, list):
            sites.update(str(item) for item in value if item)
        elif notice.source_site:
            sites.add(notice.source_site)
    return sorted(sites)
