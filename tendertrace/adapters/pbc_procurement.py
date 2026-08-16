from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx
from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import (
    Attachment,
    Notice,
    _clean_spaces,
    _matches_bidql,
    _summarize,
)
from tendertrace.fetching import FetchError, FetchPolicy, FetchResult, ManagedFetcher
from tendertrace.intent.region import parse_region
from tendertrace.parsing import select_main_content
from tendertrace.pipeline.artifacts import page_artifact_from_fetch


PBC_PROCUREMENT_HOME = "https://jzcg.pbc.gov.cn/"
PBC_PROCUREMENT_LIST_URL = (
    "https://jzcg.pbc.gov.cn/freecms/site/templet/jzcggg/index.html"
)
PBC_PROCUREMENT_API = (
    "https://jzcg.pbc.gov.cn/freecms/rest/v1/notice/selectInfoMoreChannel.do"
)
PBC_SITE_ID = "9e9a312c-e98f-4516-95ff-74af73e2f6c4"
PBC_CHANNEL_ID = "4081b14c-c0a5-4585-ae0f-60c72b29beb0"
PBC_AUTHORITY = "中国人民银行集中采购中心"


def parse_notice_payload(payload: dict[str, Any]) -> list[Notice]:
    rows = payload.get("data")
    if str(payload.get("code")) != "200" or not isinstance(rows, list):
        raise ValueError("unexpected PBC procurement response schema")
    notices: list[Notice] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = row.get("fieldValues")
        if not isinstance(values, dict):
            values = {}
        notice_id = _text(row.get("id"))
        title = _text(row.get("title") or values.get("f_noticeName"))
        publish_time = _text(values.get("f_noticeTime"))[:10]
        page_url = _text(row.get("pageurl"))
        notice_type = _text(values.get("f_noticeType"))
        if not notice_id or not title or not publish_time or not page_url:
            continue
        source_url = urljoin(PBC_PROCUREMENT_HOME, page_url)
        source_url = f"{source_url}?{urlencode({'noticeId': notice_id, 'noticeType': notice_type, 'Type': 'jzcggg'})}"
        purchaser = _text(values.get("f_purchaser"))
        purchaser_address = _text(values.get("f_purchaserAddr"))
        catalogue = _text(values.get("f_catalogueNameList"))
        region = _infer_region(f"{title} {purchaser} {purchaser_address}")
        attachments = _attachments(values.get("attachList"), source_url)
        fields = {
            "cluster_key": f"pbc_procurement:{notice_id}",
            "authority": PBC_AUTHORITY,
            "notice_type": _text(values.get("f_noticeTypeName")),
            "notice_type_code": notice_type,
            "project_code": _text(values.get("f_openTenderCode")),
            "plan_code": _text(values.get("f_planCodes")),
            "budget": _text(values.get("f_budget")),
            "deadline": _text(values.get("f_expireTime")),
            "open_tender_time": _text(values.get("f_openTenderTime")),
            "catalogue": catalogue,
            "purchaser_address": purchaser_address,
            "agency": _text(values.get("f_agency")),
            "official_region": _text(values.get("f_regionName")),
            "landing_page": PBC_PROCUREMENT_LIST_URL,
        }
        metadata = _metadata_content(title, purchaser, values)
        notices.append(
            Notice(
                id=notice_id,
                source_site="pbc_procurement",
                title=title,
                publish_time=publish_time,
                region=region,
                purchaser=purchaser,
                source_url=source_url,
                content_text=metadata,
                core_content=metadata[:600],
                attachments=attachments,
                fields={key: value for key, value in fields.items() if value not in ("", None)},
            )
        )
    return notices


def enrich_from_detail(
    notice: Notice,
    html: str,
    fetch_result: FetchResult | None = None,
) -> Notice:
    parser = HTMLParser(html)
    selection = select_main_content(parser, ("#noticeArea", "#content", ".info-article"))
    content = selection.text or notice.content_text
    attachments = list(notice.attachments)
    seen = {item.url for item in attachments}
    for anchor in parser.css("#noticeArea a[href], #content a[href], .info-article a[href]"):
        href = anchor.attributes.get("href", "")
        label = _clean_spaces(anchor.text(separator=" "))
        lowered = href.casefold()
        if not href or not (
            any(ext in lowered for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"))
            or "附件" in label
        ):
            continue
        attachment_url = urljoin(notice.source_url, href)
        if attachment_url in seen:
            continue
        seen.add(attachment_url)
        attachments.append(Attachment(name=label or href.rsplit("/", 1)[-1], url=attachment_url))
    fields = {
        **notice.fields,
        "content_length": len(content),
        "content_selector": selection.selector,
        "content_fallback": selection.fallback_used,
    }
    if fetch_result is not None:
        fields["page_artifact"] = page_artifact_from_fetch(notice.source_site, fetch_result)
    return Notice(
        id=notice.id,
        source_site=notice.source_site,
        title=notice.title,
        publish_time=notice.publish_time,
        region=notice.region,
        purchaser=notice.purchaser,
        source_url=notice.source_url,
        content_text=content,
        core_content=_summarize(content),
        attachments=attachments,
        fields=fields,
    )


class PbcProcurementAdapter:
    name = "pbc_procurement"

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.policy = FetchPolicy(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
                "Referer": PBC_PROCUREMENT_LIST_URL,
            },
            timeout=timeout,
            max_retries=2,
        )
        self.transport = transport
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") not in {
            "global", "eu", "worldbank", "uk", "idb", "adb", "afdb", "ebrd",
            "canada", "ukraine",
        }

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        if max_pages < 1 or max_results < 1:
            return []
        with ManagedFetcher(self.policy, transport=self.transport) as fetcher:
            try:
                candidates: list[Notice] = []
                seen: set[str] = set()
                for start, end in _date_chunks(bidql):
                    for page in range(1, max_pages + 1):
                        response = fetcher.get(
                            PBC_PROCUREMENT_API,
                            params=_query_params(start, end, page),
                        )
                        response.raise_for_status()
                        for notice in parse_notice_payload(response.json()):
                            if notice.id not in seen:
                                seen.add(notice.id)
                                candidates.append(notice)
                matched = [notice for notice in candidates if _matches_bidql(notice, bidql)]
                batch = matched[:max_results]
                details = fetcher.batch_get([notice.source_url for notice in batch])
                return [
                    _enrich_or_keep(notice, detail)
                    for notice, detail in zip(batch, details, strict=True)
                ]
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()


def _query_params(start: date, end: date, page: int) -> dict[str, str | int]:
    return {
        "siteId": PBC_SITE_ID,
        "channel": PBC_CHANNEL_ID,
        "noticeType": "",
        "currPage": page,
        "pageSize": 10,
        "operationStartTime": f"{start.isoformat()} 00:00:00",
        "operationEndTime": f"{end.isoformat()} 23:59:59",
        "title": "",
        "purchaseManner": "",
        "purchasingtype": "1",
        "selectTimeName": "noticeTime",
    }


def _date_chunks(bidql: dict[str, Any]) -> list[tuple[date, date]]:
    window = bidql.get("time", {}).get("resolved_window")
    today = date.today()
    if not isinstance(window, dict) or not window.get("from") or not window.get("to"):
        return [(today - timedelta(days=30), today)]
    start = date.fromisoformat(str(window["from"]))
    end = date.fromisoformat(str(window["to"]))
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=364), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _infer_region(text: str) -> str:
    value = parse_region(text).value
    return str(value.get("city") or value.get("province") or "全国")


def _metadata_content(title: str, purchaser: str, values: dict[str, Any]) -> str:
    labels = (
        ("项目", title),
        ("采购人", purchaser),
        ("公告类型", values.get("f_noticeTypeName")),
        ("采购品类", values.get("f_catalogueNameList")),
        ("项目编号", values.get("f_openTenderCode")),
        ("预算", values.get("f_budget")),
        ("开标时间", values.get("f_openTenderTime")),
        ("采购人地址", values.get("f_purchaserAddr")),
    )
    return "；".join(f"{label}：{_text(value)}" for label, value in labels if _text(value))


def _attachments(value: Any, source_url: str) -> list[Attachment]:
    if not value:
        return []
    try:
        rows = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return []
    if not isinstance(rows, list):
        return []
    attachments: list[Attachment] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        href = _text(row.get("url") or row.get("fileUrl") or row.get("path"))
        if href:
            attachments.append(
                Attachment(
                    name=_text(row.get("name") or row.get("fileName")) or href.rsplit("/", 1)[-1],
                    url=urljoin(source_url, href),
                )
            )
    return attachments


def _enrich_or_keep(notice: Notice, detail: FetchResult) -> Notice:
    try:
        detail.raise_for_status()
        return enrich_from_detail(notice, detail.text, detail)
    except FetchError as exc:
        return Notice(
            id=notice.id,
            source_site=notice.source_site,
            title=notice.title,
            publish_time=notice.publish_time,
            region=notice.region,
            purchaser=notice.purchaser,
            source_url=notice.source_url,
            content_text=notice.content_text,
            core_content=notice.core_content,
            attachments=notice.attachments,
            fields={**notice.fields, "detail_error": str(exc)},
        )


def _text(value: Any) -> str:
    if value is None or str(value).casefold() == "null":
        return ""
    return _clean_spaces(str(value))
