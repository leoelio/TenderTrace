from __future__ import annotations

from typing import Any

from tendertrace.adapters.ccgp import Notice, _clean_spaces
from tendertrace.fetching import FetchPolicy, ManagedFetcher


TED_SEARCH_API = "https://api.ted.europa.eu/v3/notices/search"
TED_NOTICE_BASE = "https://ted.europa.eu/en/notice"
TED_FIELDS = (
    "publication-number",
    "publication-date",
    "title-proc",
    "description-proc",
    "buyer-name",
    "place-of-performance-country-proc",
    "deadline-date-lot",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "links",
)


def build_search_body(
    bidql: dict[str, Any], *, page: int, limit: int
) -> dict[str, object] | None:
    terms = _source_terms(bidql)
    if not terms:
        return None
    clauses = [f'(title-proc ~ "{_query_term(term)}" OR description-proc ~ "{_query_term(term)}")' for term in terms[:3]]
    query = " OR ".join(clauses)
    window = bidql.get("time", {}).get("resolved_window")
    if isinstance(window, dict) and window.get("from") and window.get("to"):
        start = str(window["from"]).replace("-", "")
        end = str(window["to"]).replace("-", "")
        query = f"({query}) AND publication-date >= {start} AND publication-date <= {end}"
    return {
        "query": query,
        "fields": list(TED_FIELDS),
        "scope": "ACTIVE",
        "limit": min(max(limit, 1), 250),
        "page": page,
        "paginationMode": "PAGE_NUMBER",
    }


def parse_notices(payload: dict[str, Any]) -> list[Notice]:
    records = payload.get("notices")
    if not isinstance(records, list):
        return []
    notices: list[Notice] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        notice_id = str(record.get("publication-number") or "").strip()
        title = _localized_text(record.get("title-proc"))
        if not notice_id or not title:
            continue
        description = _localized_text(record.get("description-proc"))
        buyer = _localized_text(record.get("buyer-name"))
        countries = record.get("place-of-performance-country-proc")
        region = ", ".join(str(item) for item in countries) if isinstance(countries, list) else ""
        source_url = _preferred_link(record.get("links")) or f"{TED_NOTICE_BASE}/{notice_id}/html"
        deadline = _first_value(record.get("deadline-date-lot"))
        notices.append(
            Notice(
                id=notice_id,
                source_site="ted",
                title=title,
                publish_time=str(record.get("publication-date") or "")[:10],
                region=region,
                purchaser=buyer,
                source_url=source_url,
                content_text=description,
                core_content=(description or title)[:600],
                fields={
                    "cluster_key": f"ted:{notice_id}",
                    "deadline": deadline,
                    "estimated_value": _first_value(record.get("estimated-value-proc")),
                    "currency": _first_value(record.get("estimated-value-cur-proc")),
                    "authority": "Publications Office of the European Union",
                },
            )
        )
    return notices


class TedAdapter:
    name = "ted"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.policy = FetchPolicy(
            headers={"User-Agent": "TenderTrace/0.1 (+procurement-intelligence)"},
            timeout=timeout,
            max_retries=2,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") in {"global", "eu"}

    def collect(
        self, bidql: dict[str, Any], *, max_pages: int = 1, max_results: int = 10
    ) -> list[Notice]:
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy) as fetcher:
            try:
                for page in range(1, max_pages + 1):
                    body = build_search_body(bidql, page=page, limit=max_results)
                    if body is None:
                        return []
                    response = fetcher.post(TED_SEARCH_API, json=body)
                    response.raise_for_status()
                    for notice in parse_notices(response.json()):
                        if notice.id in seen:
                            continue
                        seen.add(notice.id)
                        notices.append(notice)
                        if len(notices) >= max_results:
                            return notices
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()
        return notices


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or []
    return [str(value).strip() for value in values if str(value).strip()]


def _query_term(value: str) -> str:
    return value.replace("\\", " ").replace('"', " ").strip()


def _localized_text(value: object) -> str:
    if isinstance(value, dict):
        for language in ("eng", "ENG", "en"):
            if language in value:
                return _first_value(value[language])
        for item in value.values():
            text = _first_value(item)
            if text:
                return text
    return _first_value(value)


def _first_value(value: object) -> str:
    if isinstance(value, list):
        return _first_value(value[0]) if value else ""
    return _clean_spaces(str(value or ""))


def _preferred_link(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    for kind in ("htmlDirect", "html", "pdf"):
        links = value.get(kind)
        if not isinstance(links, dict):
            continue
        for language in ("ENG", "MUL"):
            if links.get(language):
                return str(links[language])
        if links:
            return str(next(iter(links.values())))
    return ""
