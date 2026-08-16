from __future__ import annotations

import csv
from io import StringIO
import re
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces, _make_notice_id
from tendertrace.fetching import FetchPolicy, ManagedFetcher


CANADABUYS_OPEN_TENDERS_URL = (
    "https://canadabuys.canada.ca/opendata/pub/"
    "openTenderNotice-ouvertAvisAppelOffres.csv"
)

_TITLE = "title-titre-eng"
_REFERENCE = "referenceNumber-numeroReference"
_PUBLICATION_DATE = "publicationDate-datePublication"
_DEADLINE = "tenderClosingDate-appelOffresDateCloture"
_NOTICE_URL = "noticeURL-URLavis-eng"
_DESCRIPTION = "tenderDescription-descriptionAppelOffres-eng"
_ATTACHMENTS = "attachment-piecesJointes-eng"
_REQUIRED_COLUMNS = {_TITLE, _REFERENCE, _PUBLICATION_DATE, _NOTICE_URL}


def parse_open_tenders(
    text: str,
    bidql: dict[str, Any],
    *,
    max_results: int = 10,
) -> list[Notice]:
    reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    columns = set(reader.fieldnames or [])
    if not _REQUIRED_COLUMNS.issubset(columns):
        raise ValueError("CanadaBuys open tender CSV schema is not recognized")
    terms = _source_terms(bidql)
    notices: list[Notice] = []
    for row in reader:
        notice = _notice_from_row(row)
        if notice is None or not _in_window(notice.publish_time, bidql):
            continue
        if terms and not _matches_terms(notice, terms):
            continue
        notices.append(notice)
    notices.sort(key=lambda item: (item.publish_time, item.id), reverse=True)
    return notices[: max(0, max_results)]


class CanadaBuysAdapter:
    name = "canadabuys"

    def __init__(
        self,
        *,
        timeout: float = 30.0,
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
        return bidql.get("region", {}).get("scope") in {"global", "canada"}

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        del max_pages
        with ManagedFetcher(self.policy, transport=self.transport) as fetcher:
            try:
                response = fetcher.get(CANADABUYS_OPEN_TENDERS_URL)
                response.raise_for_status()
                return parse_open_tenders(
                    response.text,
                    bidql,
                    max_results=max_results,
                )
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()


def _notice_from_row(row: dict[str, str]) -> Notice | None:
    title = _first(row, _TITLE, "title-titre-fra")
    reference = _first(row, _REFERENCE, "solicitationNumber-numeroSollicitation")
    source_url = _first(row, _NOTICE_URL, "noticeURL-URLavis-fra")
    publish_time = _first(row, _PUBLICATION_DATE)[:10]
    if not title or not reference or not source_url or not publish_time:
        return None
    description = _first(row, _DESCRIPTION, "tenderDescription-descriptionAppelOffres-fra")
    region = _region(row)
    purchaser = _first(
        row,
        "contractingEntityName-nomEntitContractante-eng",
        "contractingEntityName-nomEntitContractante-fra",
    )
    category = _first(
        row,
        "unspscDescription-eng",
        "gsinDescription-nibsDescription-eng",
        "procurementCategory-categorieApprovisionnement",
    )
    method = _first(row, "procurementMethod-methodeApprovisionnement-eng")
    content = _clean_spaces(" ".join(value for value in (description, category, method, region) if value))
    return Notice(
        id=f"canadabuys-{_safe_id(reference) or _make_notice_id(source_url)}",
        source_site="canadabuys",
        title=title,
        publish_time=publish_time,
        region=region or "Canada",
        purchaser=purchaser,
        source_url=source_url,
        content_text=content,
        core_content=(description or title)[:600],
        attachments=_attachments(_first(row, _ATTACHMENTS, "attachment-piecesJointes-fra")),
        fields={
            "cluster_key": f"canadabuys:{reference}",
            "reference_number": reference,
            "solicitation_number": _first(row, "solicitationNumber-numeroSollicitation"),
            "amendment_number": _first(row, "amendmentNumber-numeroModification"),
            "notice_status": _first(row, "tenderStatus-appelOffresStatut-eng"),
            "notice_type": _first(row, "noticeType-avisType-eng"),
            "procurement_method": method,
            "classification": category,
            "deadline": _first(row, _DEADLINE)[:10],
            "authority": "Public Services and Procurement Canada - CanadaBuys",
        },
    )


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or bidql.get("topic", {}).get("core") or []
    return _dedupe([_clean_spaces(str(value)).casefold() for value in values if str(value).strip()])


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


def _region(row: dict[str, str]) -> str:
    values = [
        _first(row, "regionsOfOpportunity-regionAppelOffres-eng"),
        _first(row, "regionsOfDelivery-regionsLivraison-eng"),
        _first(row, "contractingEntityAddressProvince-entiteContractanteAdresseProvince-eng"),
    ]
    return ", ".join(_dedupe([value for value in values if value])) or "Canada"


def _attachments(value: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    seen: set[str] = set()
    for url in re.findall(r"https?://[^\s,;]+", value):
        clean_url = url.rstrip(".)]>'\"")
        if not clean_url or clean_url in seen:
            continue
        seen.add(clean_url)
        name = unquote(urlsplit(clean_url).path.rsplit("/", 1)[-1]) or "Tender attachment"
        attachments.append(Attachment(name=name[:200], url=clean_url))
    return attachments


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _clean_spaces(str(row.get(key) or ""))
        if value:
            return value
    return ""


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")[:120]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
