from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces
from tendertrace.fetching import FetchPolicy, ManagedFetcher


PROZORRO_FEED_URL = "https://public.api.openprocurement.org/api/2.5/tenders"
PROZORRO_PORTAL_URL = "https://prozorro.gov.ua/tender"
_TENDER_ID = re.compile(r"^[a-f0-9]{32}$", flags=re.IGNORECASE)

_UKRAINIAN_TOPIC_ALIASES = {
    "charging": ("зарядн", "електромобіл"),
    "server": ("сервер", "обчислювальн"),
    "air conditioning": ("кондиціон", "вентиляц", "охолоджен"),
    "hvac": ("кондиціон", "вентиляц", "охолоджен"),
    "energy storage": ("накопичувач енергії", "акумулятор"),
    "medical": ("медичне обладнання", "медичн"),
    "elevator": ("ліфт", "ескалатор"),
    "fire": ("пожежн",),
    "security": ("система безпеки", "відеоспостереж"),
    "network": ("мережеве обладнання", "маршрутизатор", "комутатор"),
}


def build_feed_url(
    bidql: dict[str, Any],
    *,
    limit: int,
    offset: str = "",
) -> str:
    params: dict[str, object] = {"descending": 1, "limit": min(max(limit, 1), 1000)}
    if offset:
        params["offset"] = offset
    else:
        window = bidql.get("time", {}).get("resolved_window")
        if isinstance(window, dict) and window.get("to"):
            params["offset"] = f"{window['to']}T23:59:59+03:00"
    return f"{PROZORRO_FEED_URL}?{urlencode(params)}"


def parse_tender(payload: dict[str, Any]) -> Notice | None:
    tender = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(tender, dict):
        return None
    internal_id = _text(tender.get("id"))
    tender_id = _text(tender.get("tenderID"))
    title = _text(tender.get("title_en")) or _text(tender.get("title"))
    if not internal_id or not tender_id or not title:
        return None
    description = _text(tender.get("description_en")) or _text(tender.get("description"))
    item_text, classification, region = _item_summary(tender.get("items"))
    purchaser, purchaser_region = _purchaser(tender.get("procuringEntity"))
    value = tender.get("value") if isinstance(tender.get("value"), dict) else {}
    period = tender.get("tenderPeriod") if isinstance(tender.get("tenderPeriod"), dict) else {}
    content = _clean_spaces(" ".join(value for value in (description, item_text, classification) if value))
    return Notice(
        id=f"prozorro-{internal_id}",
        source_site="prozorro",
        title=title,
        publish_time=_published_date(tender),
        region=region or purchaser_region or "Ukraine",
        purchaser=purchaser,
        source_url=f"{PROZORRO_PORTAL_URL}/{tender_id}",
        content_text=content,
        core_content=(description or item_text or title)[:600],
        attachments=_documents(tender.get("documents")),
        fields={
            "cluster_key": f"prozorro:{tender_id}",
            "tender_id": tender_id,
            "notice_status": _text(tender.get("status")),
            "procurement_method": _text(tender.get("procurementMethodType"))
            or _text(tender.get("procurementMethod")),
            "classification": classification,
            "deadline": _text(period.get("endDate"))[:10],
            "estimated_value": _number_text(value.get("amount")),
            "currency": _text(value.get("currency")),
            "authority": "Prozorro public procurement system",
        },
    )


class ProzorroAdapter:
    name = "prozorro"

    def __init__(
        self,
        *,
        timeout: float = 25.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.policy = FetchPolicy(
            headers={"User-Agent": "TenderTrace/0.1 (+procurement-intelligence)"},
            timeout=timeout,
            max_retries=2,
        )
        self.transport = transport
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") in {"global", "ukraine"}

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        terms = _source_terms(bidql)
        page_limit = min(100, max(20, max_results * 4))
        page_url = build_feed_url(bidql, limit=page_limit)
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy, transport=self.transport) as fetcher:
            try:
                for _page in range(max(1, max_pages)):
                    feed_response = fetcher.get(page_url)
                    feed_response.raise_for_status()
                    feed = feed_response.json()
                    rows = feed.get("data") if isinstance(feed, dict) else None
                    if not isinstance(rows, list) or not rows:
                        break
                    detail_urls = [
                        f"{PROZORRO_FEED_URL}/{tender_id}"
                        for row in rows
                        if isinstance(row, dict)
                        and _TENDER_ID.fullmatch(tender_id := _text(row.get("id")))
                    ]
                    for response in fetcher.batch_get(detail_urls, max_workers=6):
                        if not response.ok:
                            continue
                        notice = parse_tender(response.json())
                        if (
                            notice is None
                            or notice.id in seen
                            or not _in_window(notice.publish_time, bidql)
                            or (terms and not _matches_terms(notice, terms))
                        ):
                            continue
                        seen.add(notice.id)
                        notices.append(notice)
                        if len(notices) >= max_results:
                            return notices
                    if _feed_before_window(rows, bidql):
                        break
                    page_url = _next_page_url(feed)
                    if not page_url:
                        break
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()
        return notices


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    raw = bidql.get("topic", {}).get("source_terms") or bidql.get("topic", {}).get("core") or []
    terms = [_clean_spaces(str(value)).casefold() for value in raw if str(value).strip()]
    for term in tuple(terms):
        for key, aliases in _UKRAINIAN_TOPIC_ALIASES.items():
            if key in term or term in key:
                terms.extend(aliases)
    return list(dict.fromkeys(terms))


def _matches_terms(notice: Notice, terms: list[str]) -> bool:
    haystack = " ".join(
        (notice.title, notice.content_text, notice.core_content, notice.purchaser, notice.region)
    ).casefold()
    return any(term in haystack for term in terms)


def _in_window(publish_time: str, bidql: dict[str, Any]) -> bool:
    window = bidql.get("time", {}).get("resolved_window")
    if not isinstance(window, dict) or not window.get("from") or not window.get("to"):
        return True
    return str(window["from"]) <= publish_time[:10] <= str(window["to"])


def _feed_before_window(rows: list[object], bidql: dict[str, Any]) -> bool:
    window = bidql.get("time", {}).get("resolved_window")
    if not isinstance(window, dict) or not window.get("from"):
        return False
    modified = [
        _text(row.get("dateModified"))[:10]
        for row in rows
        if isinstance(row, dict) and _text(row.get("dateModified"))
    ]
    return bool(modified and min(modified) < str(window["from"]))


def _next_page_url(feed: dict[str, Any]) -> str:
    next_page = feed.get("next_page")
    if not isinstance(next_page, dict):
        return ""
    value = _text(next_page.get("uri")) or _text(next_page.get("path"))
    if not value:
        return ""
    parsed = urlsplit(value)
    return urlunsplit(("https", "public.api.openprocurement.org", parsed.path, parsed.query, ""))


def _published_date(tender: dict[str, Any]) -> str:
    for key in ("noticePublicationDate", "date", "dateCreated", "dateModified"):
        value = _text(tender.get(key))
        if value:
            return value[:10]
    return ""


def _purchaser(value: object) -> tuple[str, str]:
    if not isinstance(value, dict):
        return "", ""
    address = value.get("address") if isinstance(value.get("address"), dict) else {}
    return _text(value.get("name")), _address_text(address)


def _item_summary(value: object) -> tuple[str, str, str]:
    if not isinstance(value, list):
        return "", "", ""
    descriptions: list[str] = []
    classifications: list[str] = []
    regions: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        description = _text(item.get("description"))
        if description:
            descriptions.append(description)
        classification = item.get("classification")
        if isinstance(classification, dict):
            label = _clean_spaces(
                " ".join(
                    value
                    for value in (_text(classification.get("id")), _text(classification.get("description")))
                    if value
                )
            )
            if label:
                classifications.append(label)
        address = item.get("deliveryAddress")
        if isinstance(address, dict):
            region = _address_text(address)
            if region:
                regions.append(region)
    return (
        " ".join(dict.fromkeys(descriptions)),
        ", ".join(dict.fromkeys(classifications)),
        ", ".join(dict.fromkeys(regions)),
    )


def _address_text(address: dict[str, Any]) -> str:
    values = [
        _text(address.get(key))
        for key in ("locality", "region", "countryName")
        if _text(address.get(key))
    ]
    return ", ".join(dict.fromkeys(values))


def _documents(value: object) -> list[Attachment]:
    if not isinstance(value, list):
        return []
    documents: list[Attachment] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        url = _text(item.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        documents.append(
            Attachment(
                name=_text(item.get("title")) or _text(item.get("description")) or "Tender document",
                url=url,
            )
        )
    return documents


def _text(value: object) -> str:
    return _clean_spaces(str(value or ""))


def _number_text(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _text(value)
    return str(int(number)) if number.is_integer() else str(number)
