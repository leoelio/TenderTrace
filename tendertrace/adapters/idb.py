from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from tendertrace.adapters.ccgp import Notice, _clean_spaces
from tendertrace.fetching import FetchPolicy, ManagedFetcher


IDB_DATASTORE_API = "https://data.iadb.org/api/action/datastore_search_sql"
IDB_RESOURCE_ID = "856aabfd-2c6a-48fb-a8b8-19f3ff443618"


def build_search_url(bidql: dict[str, Any], *, page: int, limit: int) -> str | None:
    terms = _source_terms(bidql)
    if not terms:
        return None
    fields = ("noticetitle", "projectname", "sectorenglnm", "process_desc")
    term_clauses = []
    for term in terms[:3]:
        pattern = _sql_pattern(term)
        if not pattern:
            continue
        term_clauses.append(
            "(" + " OR ".join(f'lower("{field}") LIKE \'%{pattern}%\'' for field in fields) + ")"
        )
    if not term_clauses:
        return None
    clauses = ["(" + " OR ".join(term_clauses) + ")"]
    window = bidql.get("time", {}).get("resolved_window")
    if isinstance(window, dict) and window.get("from") and window.get("to"):
        start = _sql_literal(str(window["from"]))
        end = _sql_literal(str(window["to"]))
        clauses.append(f'"publicationdate" >= \'{start}\'')
        clauses.append(f'"publicationdate" <= \'{end} 23:59:59.999999999\'')
    page_size = min(max(limit, 1), 100)
    offset = max(page - 1, 0) * page_size
    sql = (
        f'SELECT * FROM "{IDB_RESOURCE_ID}" WHERE '
        + " AND ".join(clauses)
        + f' ORDER BY "publicationdate" DESC LIMIT {page_size} OFFSET {offset}'
    )
    return f"{IDB_DATASTORE_API}?{urlencode({'sql': sql})}"


def parse_notices(payload: dict[str, Any]) -> list[Notice]:
    result = payload.get("result")
    records = result.get("records") if isinstance(result, dict) else None
    if not isinstance(records, list):
        return []
    notices: list[Notice] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        notice_id = _text(record.get("noticeid"))
        title = _text(record.get("noticetitle"))
        if not notice_id or not title:
            continue
        project_name = _text(record.get("projectname"))
        notice_type = _text(record.get("type"))
        sector = _text(record.get("sectorenglnm") or record.get("sector"))
        process_description = _text(record.get("process_desc"))
        content = " | ".join(
            value for value in (project_name, notice_type, sector, process_description) if value
        )
        document_url = _text(record.get("documenturl"))
        project_url = _text(record.get("proyecturl"))
        source_url = document_url or project_url
        if not source_url:
            continue
        notices.append(
            Notice(
                id=notice_id,
                source_site="idb",
                title=title,
                publish_time=_text(record.get("publicationdate"))[:10],
                region=_text(record.get("countryname")),
                purchaser="",
                source_url=source_url,
                content_text=content,
                core_content=(content or title)[:600],
                fields={
                    "cluster_key": f"idb:{notice_id}",
                    "notice_type": notice_type,
                    "project_id": _text(record.get("projectnumber")),
                    "project_name": project_name,
                    "project_url": project_url,
                    "loan_number": _text(record.get("loannumber")),
                    "deadline": _text(record.get("deadline"))[:10],
                    "sector": sector,
                    "procurement_method": _text(record.get("prcrmnt_mthd_engl_nm")),
                    "process_name": _text(record.get("process_nm")),
                    "authority": "Inter-American Development Bank",
                },
            )
        )
    return notices


class IdbAdapter:
    name = "idb"

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.policy = FetchPolicy(
            headers={"User-Agent": "TenderTrace/0.1 (+procurement-intelligence)"},
            timeout=timeout,
            max_retries=2,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") in {"global", "idb"}

    def collect(
        self, bidql: dict[str, Any], *, max_pages: int = 1, max_results: int = 10
    ) -> list[Notice]:
        page_size = min(max(max_results, 10), 100)
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy) as fetcher:
            try:
                for page in range(1, max_pages + 1):
                    url = build_search_url(bidql, page=page, limit=page_size)
                    if url is None:
                        return []
                    response = fetcher.get(url)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or payload.get("success") is not True:
                        raise RuntimeError("IDB DataStore API returned an unsuccessful response")
                    batch = parse_notices(payload)
                    for notice in batch:
                        if notice.id in seen or not _in_window(notice.publish_time, bidql):
                            continue
                        seen.add(notice.id)
                        notices.append(notice)
                        if len(notices) >= max_results:
                            return notices
                    if len(batch) < page_size:
                        break
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()
        return notices


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or []
    return [str(value).strip() for value in values if str(value).strip()]


def _sql_pattern(value: str) -> str:
    return _sql_literal(
        value.casefold().replace("%", " ").replace("_", " ").replace("\\", " ").strip()
    )


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _in_window(publish_time: str, bidql: dict[str, Any]) -> bool:
    window = bidql.get("time", {}).get("resolved_window")
    if not isinstance(window, dict) or not window.get("from") or not window.get("to"):
        return True
    return str(window["from"]) <= publish_time[:10] <= str(window["to"])


def _text(value: object) -> str:
    return _clean_spaces(str(value or ""))
