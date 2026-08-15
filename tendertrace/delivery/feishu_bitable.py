from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from tendertrace.config import Settings


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
REQUIRED_FIELDS = (
    "标题",
    "公告ID",
    "地区",
    "关键词",
    "发布时间",
    "截止时间",
    "预算",
    "来源",
    "来源链接",
    "状态",
    "Word 报告",
    "项目指纹",
    "运行ID",
    "采购人",
    "附件链接",
    "首次发现时间",
    "最近同步时间",
    "机会等级",
    "机会评分",
    "信息完整度",
    "信息可信度",
    "时效评分",
    "销售阶段",
    "项目目标",
    "建议策略",
    "跟进建议",
    "风险提示",
    "市场价格位置",
    "市场样本数",
    "竞争情报",
    "竞争证据",
    "历史竞争者",
    "需求覆盖率",
    "需求待核对",
    "需求优化建议",
    "机会负责人",
    "协同状态",
    "下一步行动",
    "飞书任务ID",
    "飞书日程ID",
    "协同更新时间",
    "线索正文",
    "伙伴提交人",
    "来源核验",
    "核验时间",
    "核验摘要",
)


@dataclass(frozen=True)
class FeishuBitableResult:
    status: str
    channel: str = "feishu_bitable"
    record_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    message: str = ""
    app_token: str = ""
    table_id: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("app_token", None)
        data["app_token_configured"] = bool(self.app_token)
        return data


@dataclass(frozen=True)
class FeishuBitableCheckResult:
    status: str
    message: str
    table_id: str = ""
    table_name: str = ""
    field_count: int = 0
    record_count: int = 0
    missing_fields: tuple[str, ...] = ()
    created_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def check_feishu_bitable(
    settings: Settings,
    *,
    ensure_fields: bool = False,
    http_client_factory=httpx.Client,
) -> FeishuBitableCheckResult:
    missing_settings = _missing_settings(settings)
    if missing_settings:
        return FeishuBitableCheckResult(
            status="skipped",
            message=f"missing Feishu settings: {', '.join(missing_settings)}",
        )
    try:
        with _client_context(http_client_factory, settings.feishu_timeout) as client:
            token = _tenant_access_token(settings, client)
            table_name = _table_name(settings, client, token)
            fields = _list_fields(settings, client, token)
            record_count = _record_count(settings, client, token)
            missing_fields = tuple(field for field in REQUIRED_FIELDS if field not in fields)
            created_fields: tuple[str, ...] = ()
            if ensure_fields and missing_fields:
                created: list[str] = []
                try:
                    for field in missing_fields:
                        created.append(_create_text_field(settings, client, token, field))
                except Exception as exc:
                    return FeishuBitableCheckResult(
                        status="failed",
                        message=f"cannot create missing fields: {type(exc).__name__}: {exc}",
                        table_id=settings.feishu_bitable_table_id,
                        table_name=table_name,
                        field_count=len(fields),
                        record_count=record_count,
                        missing_fields=missing_fields,
                        created_fields=tuple(created),
                    )
                created_fields = tuple(created)
                fields = _list_fields(settings, client, token)
                missing_fields = tuple(field for field in REQUIRED_FIELDS if field not in fields)
    except Exception as exc:
        return FeishuBitableCheckResult(
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
            table_id=settings.feishu_bitable_table_id,
        )
    status = "pass" if not missing_fields else "warn"
    message = "Feishu bitable is ready" if status == "pass" else "required fields are missing"
    return FeishuBitableCheckResult(
        status=status,
        message=message,
        table_id=settings.feishu_bitable_table_id,
        table_name=table_name,
        field_count=len(fields),
        record_count=record_count,
        missing_fields=missing_fields,
        created_fields=created_fields,
    )


def sync_notices_to_bitable(
    settings: Settings,
    *,
    notices: list[dict[str, Any]],
    bidql: dict[str, Any],
    query: str,
    run_id: str,
    outbox_path: Path,
    synced_at: datetime | None = None,
    http_client_factory=httpx.Client,
) -> FeishuBitableResult:
    if "feishu_bitable" not in settings.delivery_channels:
        return FeishuBitableResult(status="skipped", message="feishu_bitable channel is disabled")
    missing_settings = _missing_settings(settings)
    if missing_settings:
        return FeishuBitableResult(
            status="skipped",
            message=f"missing Feishu settings: {', '.join(missing_settings)}",
            app_token=settings.feishu_bitable_app_token,
            table_id=settings.feishu_bitable_table_id,
        )
    if not notices:
        return FeishuBitableResult(
            status="skipped",
            message="no notices to sync",
            app_token=settings.feishu_bitable_app_token,
            table_id=settings.feishu_bitable_table_id,
        )
    try:
        with _client_context(http_client_factory, settings.feishu_timeout) as client:
            token = _tenant_access_token(settings, client)
            fields = _list_fields(settings, client, token)
            missing_fields = [field for field in REQUIRED_FIELDS if field not in fields]
            if missing_fields:
                return FeishuBitableResult(
                    status="failed",
                    message=f"missing Feishu fields: {', '.join(missing_fields)}",
                    app_token=settings.feishu_bitable_app_token,
                    table_id=settings.feishu_bitable_table_id,
                )
            existing = _existing_records_by_cluster(settings, client, token)
            rows = [
                _record_fields(
                    notice,
                    bidql=bidql,
                    query=query,
                    run_id=run_id,
                    outbox_path=outbox_path,
                    settings=settings,
                    synced_at=synced_at or datetime.now().astimezone(),
                )
                for notice in notices
            ]
            to_create = []
            to_update: list[tuple[str, dict[str, object]]] = []
            for row in rows:
                cluster_key = str(row["项目指纹"])
                record_id = existing.get(cluster_key)
                if record_id:
                    to_update.append((record_id, _update_fields(row)))
                else:
                    to_create.append(row)
            created_count = _batch_create_records(settings, client, token, to_create)
            updated_count = sum(
                _update_record(settings, client, token, record_id, fields)
                for record_id, fields in to_update
            )
    except Exception as exc:
        return FeishuBitableResult(
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
            app_token=settings.feishu_bitable_app_token,
            table_id=settings.feishu_bitable_table_id,
        )
    return FeishuBitableResult(
        status="sent",
        record_count=created_count + updated_count,
        created_count=created_count,
        updated_count=updated_count,
        app_token=settings.feishu_bitable_app_token,
        table_id=settings.feishu_bitable_table_id,
    )


def update_opportunity_workflow_in_bitable(
    settings: Settings,
    *,
    notice_id: str,
    workflow: dict[str, object],
    http_client_factory=httpx.Client,
) -> FeishuBitableResult:
    missing_settings = _missing_settings(settings)
    if missing_settings:
        return FeishuBitableResult(
            status="skipped",
            message=f"missing Feishu settings: {', '.join(missing_settings)}",
            app_token=settings.feishu_bitable_app_token,
            table_id=settings.feishu_bitable_table_id,
        )
    try:
        with _client_context(http_client_factory, settings.feishu_timeout) as client:
            token = _tenant_access_token(settings, client)
            fields = _list_fields(settings, client, token)
            workflow_fields = _workflow_fields(workflow)
            missing_fields = [name for name in workflow_fields if name not in fields]
            if missing_fields:
                return FeishuBitableResult(
                    status="failed",
                    message=f"missing Feishu fields: {', '.join(missing_fields)}",
                    app_token=settings.feishu_bitable_app_token,
                    table_id=settings.feishu_bitable_table_id,
                )
            record_id = _existing_records_by_notice_id(settings, client, token).get(notice_id)
            if not record_id:
                return FeishuBitableResult(
                    status="skipped",
                    message="opportunity has not been synced to Feishu bitable",
                    app_token=settings.feishu_bitable_app_token,
                    table_id=settings.feishu_bitable_table_id,
                )
            updated_count = _update_record(
                settings,
                client,
                token,
                record_id,
                workflow_fields,
            )
    except Exception as exc:
        return FeishuBitableResult(
            status="failed",
            message=f"{type(exc).__name__}: {exc}",
            app_token=settings.feishu_bitable_app_token,
            table_id=settings.feishu_bitable_table_id,
        )
    return FeishuBitableResult(
        status="sent",
        record_count=updated_count,
        updated_count=updated_count,
        app_token=settings.feishu_bitable_app_token,
        table_id=settings.feishu_bitable_table_id,
    )


def list_feishu_bitable_records(
    settings: Settings,
    *,
    http_client_factory=httpx.Client,
) -> list[dict[str, Any]]:
    missing_settings = _missing_settings(settings)
    if missing_settings:
        raise RuntimeError(f"missing Feishu settings: {', '.join(missing_settings)}")
    with _client_context(http_client_factory, settings.feishu_timeout) as client:
        token = _tenant_access_token(settings, client)
        records: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = _request_json(
                client.get(
                    _table_url(settings, "records"),
                    params=params,
                    headers=_auth_header(token),
                )
            )
            records.extend(_items(data))
            if not data.get("has_more"):
                return records
            page_token = str(data.get("page_token") or "")
            if not page_token:
                return records


def update_feishu_bitable_records(
    settings: Settings,
    *,
    updates: list[tuple[str, dict[str, object]]],
    http_client_factory=httpx.Client,
) -> int:
    if not updates:
        return 0
    missing_settings = _missing_settings(settings)
    if missing_settings:
        raise RuntimeError(f"missing Feishu settings: {', '.join(missing_settings)}")
    with _client_context(http_client_factory, settings.feishu_timeout) as client:
        token = _tenant_access_token(settings, client)
        return sum(
            _update_record(settings, client, token, record_id, fields)
            for record_id, fields in updates
        )


def _missing_settings(settings: Settings) -> list[str]:
    missing = []
    if not settings.feishu_app_id:
        missing.append("TENDERTRACE_FEISHU_APP_ID")
    if not settings.feishu_app_secret_present:
        missing.append("TENDERTRACE_FEISHU_APP_SECRET")
    if not settings.feishu_bitable_app_token:
        missing.append("TENDERTRACE_FEISHU_BITABLE_APP_TOKEN")
    if not settings.feishu_bitable_table_id:
        missing.append("TENDERTRACE_FEISHU_BITABLE_TABLE_ID")
    return missing


def _client_context(http_client_factory, timeout: float):
    try:
        return http_client_factory(timeout=timeout, trust_env=False)
    except TypeError:
        return http_client_factory(timeout=timeout)


def _tenant_access_token(settings: Settings, client: httpx.Client) -> str:
    payload = {
        "app_id": settings.feishu_app_id,
        "app_secret": settings.feishu_app_secret(),
    }
    data = _request_json(
        client.post(f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal", json=payload)
    )
    token = str(data.get("tenant_access_token") or "")
    if not token:
        raise RuntimeError("Feishu tenant_access_token is empty")
    return token


def _table_name(settings: Settings, client: httpx.Client, token: str) -> str:
    tables = _request_json(
        client.get(
            f"{FEISHU_API_BASE}/bitable/v1/apps/{settings.feishu_bitable_app_token}/tables",
            params={"page_size": 100},
            headers=_auth_header(token),
        )
    )
    for item in _items(tables):
        if item.get("table_id") == settings.feishu_bitable_table_id:
            return str(item.get("name") or "")
    raise RuntimeError(f"Feishu table_id not found: {settings.feishu_bitable_table_id}")


def _list_fields(settings: Settings, client: httpx.Client, token: str) -> dict[str, str]:
    data = _request_json(
        client.get(
            _table_url(settings, "fields"),
            params={"page_size": 100},
            headers=_auth_header(token),
        )
    )
    return {
        str(item.get("field_name") or ""): str(item.get("field_id") or "")
        for item in _items(data)
        if item.get("field_name")
    }


def _record_count(settings: Settings, client: httpx.Client, token: str) -> int:
    count = 0
    page_token = ""
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = _request_json(
            client.get(
                _table_url(settings, "records"),
                params=params,
                headers=_auth_header(token),
            )
        )
        for item in _items(data):
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            if _string_value(fields.get("项目指纹")) or _string_value(fields.get("公告ID")):
                count += 1
        if not data.get("has_more"):
            return count
        page_token = str(data.get("page_token") or "")
        if not page_token:
            return count


def _create_text_field(
    settings: Settings,
    client: httpx.Client,
    token: str,
    field_name: str,
) -> str:
    data = _request_json(
        client.post(
            _table_url(settings, "fields"),
            json={"field_name": field_name, "type": 1},
            headers=_auth_header(token),
        )
    )
    field = data.get("field") if isinstance(data.get("field"), dict) else {}
    return str(field.get("field_name") or field_name)


def _existing_records_by_cluster(
    settings: Settings,
    client: httpx.Client,
    token: str,
) -> dict[str, str]:
    existing: dict[str, str] = {}
    page_token = ""
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = _request_json(
            client.get(
                _table_url(settings, "records"),
                params=params,
                headers=_auth_header(token),
            )
        )
        for item in _items(data):
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            cluster_key = _string_value(fields.get("项目指纹"))
            record_id = str(item.get("record_id") or "")
            if cluster_key and record_id:
                existing[cluster_key] = record_id
        if not data.get("has_more"):
            return existing
        page_token = str(data.get("page_token") or "")
        if not page_token:
            return existing


def _existing_records_by_notice_id(
    settings: Settings,
    client: httpx.Client,
    token: str,
) -> dict[str, str]:
    existing: dict[str, str] = {}
    page_token = ""
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = _request_json(
            client.get(
                _table_url(settings, "records"),
                params=params,
                headers=_auth_header(token),
            )
        )
        for item in _items(data):
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            notice_id = _string_value(fields.get("公告ID"))
            record_id = str(item.get("record_id") or "")
            if notice_id and record_id:
                existing[notice_id] = record_id
        if not data.get("has_more"):
            return existing
        page_token = str(data.get("page_token") or "")
        if not page_token:
            return existing


def _batch_create_records(
    settings: Settings,
    client: httpx.Client,
    token: str,
    rows: list[dict[str, object]],
) -> int:
    if not rows:
        return 0
    created = 0
    for chunk in _chunks(rows, 500):
        data = _request_json(
            client.post(
                _table_url(settings, "records/batch_create"),
                json={"records": [{"fields": row} for row in chunk]},
                headers=_auth_header(token),
            )
        )
        created_records = _items(data)
        if not created_records:
            raise RuntimeError("Feishu batch_create returned no created records")
        created += len(created_records)
    return created


def _update_record(
    settings: Settings,
    client: httpx.Client,
    token: str,
    record_id: str,
    fields: dict[str, object],
) -> int:
    _request_json(
        client.put(
            _table_url(settings, f"records/{record_id}"),
            json={"fields": fields},
            headers=_auth_header(token),
        )
    )
    return 1


def _record_fields(
    notice: dict[str, Any],
    *,
    bidql: dict[str, Any],
    query: str,
    run_id: str,
    outbox_path: Path,
    settings: Settings,
    synced_at: datetime,
) -> dict[str, object]:
    fields = notice.get("fields") if isinstance(notice.get("fields"), dict) else {}
    structured = (
        fields.get("structured_fields") if isinstance(fields.get("structured_fields"), dict) else {}
    )
    intelligence = (
        fields.get("opportunity_intelligence")
        if isinstance(fields.get("opportunity_intelligence"), dict)
        else {}
    )
    scores = intelligence.get("scores") if isinstance(intelligence.get("scores"), dict) else {}
    market_context = (
        intelligence.get("market_context")
        if isinstance(intelligence.get("market_context"), dict)
        else {}
    )
    benchmark = (
        market_context.get("benchmark")
        if isinstance(market_context.get("benchmark"), dict)
        else {}
    )
    competition = (
        intelligence.get("competition")
        if isinstance(intelligence.get("competition"), dict)
        else {}
    )
    requirement_review = (
        intelligence.get("requirement_review")
        if isinstance(intelligence.get("requirement_review"), dict)
        else {}
    )
    cluster_key = _cluster_key(notice)
    topic = bidql.get("topic") if isinstance(bidql.get("topic"), dict) else {}
    keywords = topic.get("core") if isinstance(topic.get("core"), list) else []
    return {
        "标题": str(notice.get("title") or ""),
        "公告ID": str(notice.get("id") or ""),
        "地区": str(structured.get("region") or notice.get("region") or ""),
        "关键词": "、".join(str(item) for item in keywords) or query,
        "发布时间": str(structured.get("publish_time") or notice.get("publish_time") or ""),
        "截止时间": str(structured.get("bid_deadline") or ""),
        "预算": str(structured.get("budget") or ""),
        "来源": str(notice.get("source_site") or ""),
        "来源链接": str(notice.get("source_url") or ""),
        "状态": "新增",
        "Word 报告": _report_link(settings, outbox_path),
        "项目指纹": cluster_key,
        "运行ID": run_id,
        "采购人": str(structured.get("purchaser") or notice.get("purchaser") or ""),
        "附件链接": "\n".join(_attachment_urls(notice)),
        "首次发现时间": synced_at.isoformat(timespec="seconds"),
        "最近同步时间": synced_at.isoformat(timespec="seconds"),
        "机会等级": f"{intelligence.get('level', 'D')} · {intelligence.get('level_label', '待研判')}",
        "机会评分": str(intelligence.get("score") or 0),
        "信息完整度": str(scores.get("completeness") or 0),
        "信息可信度": str(scores.get("credibility") or 0),
        "时效评分": str(scores.get("freshness") or 0),
        "销售阶段": str(intelligence.get("stage") or "线索识别"),
        "项目目标": str(intelligence.get("project_target") or ""),
        "建议策略": str(intelligence.get("strategy") or ""),
        "跟进建议": "\n".join(_action_texts(intelligence)),
        "风险提示": "\n".join(str(item) for item in intelligence.get("risks") or []),
        "市场价格位置": str(benchmark.get("message") or "样本不足"),
        "市场样本数": str(benchmark.get("sample_count") or 0),
        "竞争情报": str(competition.get("message") or "样本不足"),
        "竞争证据": str(competition.get("evidence_excerpt") or ""),
        "历史竞争者": _competitor_text(competition),
        "需求覆盖率": (
            f"{requirement_review.get('coverage_score', 0)}/100 · "
            f"{requirement_review.get('covered_count', 0)}/"
            f"{requirement_review.get('total_count', 0)} 项"
        ),
        "需求待核对": "、".join(
            str(item) for item in requirement_review.get("missing") or []
        ),
        "需求优化建议": "\n".join(
            str(item) for item in requirement_review.get("recommendations") or []
        ),
        "机会负责人": "",
        "协同状态": "线索识别",
        "下一步行动": "",
        "飞书任务ID": "",
        "飞书日程ID": "",
        "协同更新时间": synced_at.isoformat(timespec="seconds"),
    }


def _update_fields(row: dict[str, object]) -> dict[str, object]:
    return {
        "Word 报告": row["Word 报告"],
        "运行ID": row["运行ID"],
        "最近同步时间": row["最近同步时间"],
        "机会等级": row["机会等级"],
        "机会评分": row["机会评分"],
        "信息完整度": row["信息完整度"],
        "信息可信度": row["信息可信度"],
        "时效评分": row["时效评分"],
        "销售阶段": row["销售阶段"],
        "项目目标": row["项目目标"],
        "建议策略": row["建议策略"],
        "跟进建议": row["跟进建议"],
        "风险提示": row["风险提示"],
        "市场价格位置": row["市场价格位置"],
        "市场样本数": row["市场样本数"],
        "竞争情报": row["竞争情报"],
        "竞争证据": row["竞争证据"],
        "历史竞争者": row["历史竞争者"],
        "需求覆盖率": row["需求覆盖率"],
        "需求待核对": row["需求待核对"],
        "需求优化建议": row["需求优化建议"],
    }


def _workflow_fields(workflow: dict[str, object]) -> dict[str, object]:
    return {
        "机会负责人": str(workflow.get("owner_name") or ""),
        "协同状态": str(workflow.get("stage_label") or workflow.get("stage") or ""),
        "下一步行动": str(workflow.get("next_action") or ""),
        "飞书任务ID": str(workflow.get("feishu_task_guid") or ""),
        "飞书日程ID": str(workflow.get("feishu_event_id") or ""),
        "协同更新时间": str(workflow.get("updated_at") or ""),
    }


def _action_texts(intelligence: dict[str, Any]) -> list[str]:
    actions = intelligence.get("recommended_actions")
    if not isinstance(actions, list):
        return []
    return [
        f"{item.get('role', '负责人')}：{item.get('action', '')}"
        for item in actions
        if isinstance(item, dict) and item.get("action")
    ]


def _competitor_text(competition: dict[str, Any]) -> str:
    suppliers = competition.get("historical_suppliers")
    if not isinstance(suppliers, list):
        return ""
    return "、".join(
        f"{item.get('name')}（{item.get('count', 0)} 次）"
        for item in suppliers
        if isinstance(item, dict) and item.get("name")
    )


def _attachment_urls(notice: dict[str, Any]) -> list[str]:
    attachments = notice.get("attachments")
    if not isinstance(attachments, list):
        return []
    return [
        str(item.get("url") or "")
        for item in attachments
        if isinstance(item, dict) and item.get("url")
    ]


def _cluster_key(notice: dict[str, object]) -> str:
    fields = notice.get("fields")
    if isinstance(fields, dict) and fields.get("cluster_key"):
        return str(fields["cluster_key"])
    source_site = str(notice.get("source_site") or "")
    notice_id = str(notice.get("id") or "")
    if source_site and notice_id:
        return f"{source_site}:{notice_id}"
    return str(notice.get("source_url") or notice_id)


def _report_link(settings: Settings, outbox_path: Path) -> str:
    if settings.public_base_url:
        return f"{settings.public_base_url}/api/outbox/{quote(outbox_path.name)}"
    return str(outbox_path)


def _request_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError("Feishu API returned a non-JSON response")
    code = payload.get("code")
    if code not in (None, 0):
        raise RuntimeError(f"Feishu API error {code}: {payload.get('msg')}")
    response.raise_for_status()
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("items")
    if items is None:
        items = data.get("records")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _table_url(settings: Settings, suffix: str) -> str:
    return (
        f"{FEISHU_API_BASE}/bitable/v1/apps/{settings.feishu_bitable_app_token}"
        f"/tables/{settings.feishu_bitable_table_id}/{suffix}"
    )


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_string_value(item) for item in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("link") or "")
    return str(value or "")


def _chunks(rows: list[dict[str, object]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]
