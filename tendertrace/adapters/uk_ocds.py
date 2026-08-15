from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces
from tendertrace.fetching import FetchPolicy, ManagedFetcher


CONTRACTS_FINDER_API = (
    "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
)
FIND_TENDER_API = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"


def build_search_url(api_url: str, bidql: dict[str, Any], *, limit: int) -> str:
    window = bidql.get("time", {}).get("resolved_window")
    params: dict[str, object] = {"limit": min(max(limit, 1), 100)}
    if isinstance(window, dict) and window.get("from") and window.get("to"):
        if api_url == CONTRACTS_FINDER_API:
            params.update(
                {"publishedFrom": str(window["from"]), "publishedTo": str(window["to"])}
            )
        else:
            params.update(
                {
                    "updatedFrom": f"{window['from']}T00:00:00Z",
                    "updatedTo": f"{window['to']}T23:59:59Z",
                }
            )
    return f"{api_url}?{urlencode(params)}"


def parse_ocds_notices(
    payload: dict[str, Any], *, source_site: str, authority: str
) -> list[Notice]:
    releases = payload.get("releases")
    if not isinstance(releases, list):
        return []
    notices: list[Notice] = []
    for release in releases:
        if not isinstance(release, dict):
            continue
        tender = release.get("tender")
        if not isinstance(tender, dict):
            continue
        ocid = _text(release.get("ocid"))
        release_id = _text(release.get("id")) or ocid
        title = _text(tender.get("title"))
        if not release_id or not title:
            continue
        documents = _documents(release)
        source_url = next(
            (item.url for item in documents if not _is_download(item.url)),
            documents[0].url if documents else _fallback_url(source_site),
        )
        attachments = [item for item in documents if _is_download(item.url)]
        description = _text(tender.get("description"))
        classification = tender.get("classification")
        classification_id = ""
        classification_name = ""
        if isinstance(classification, dict):
            classification_id = _text(classification.get("id"))
            classification_name = _text(classification.get("description"))
        value = tender.get("value")
        if not isinstance(value, dict):
            value = _award_value(release)
        deadline = tender.get("tenderPeriod")
        deadline_value = deadline.get("endDate") if isinstance(deadline, dict) else ""
        notices.append(
            Notice(
                id=release_id,
                source_site=source_site,
                title=title,
                publish_time=_text(release.get("date"))[:10],
                region=_delivery_region(tender),
                purchaser=_buyer_name(release),
                source_url=source_url,
                content_text=description,
                core_content=(description or title)[:600],
                attachments=attachments,
                fields={
                    "cluster_key": f"ocds:{ocid or release_id}",
                    "ocid": ocid,
                    "release_tag": ", ".join(_string_list(release.get("tag"))),
                    "notice_status": _text(tender.get("status")),
                    "procurement_method": _text(tender.get("procurementMethodDetails"))
                    or _text(tender.get("procurementMethod")),
                    "classification_id": classification_id,
                    "classification": classification_name,
                    "deadline": _text(deadline_value)[:10],
                    "estimated_value": _number_text(value.get("amount")),
                    "currency": _text(value.get("currency")),
                    "authority": authority,
                },
            )
        )
    return notices


class _UkOcdsAdapter:
    api_url = ""
    name = ""
    authority = ""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.policy = FetchPolicy(
            headers={"User-Agent": "TenderTrace/0.1 (+procurement-intelligence)"},
            timeout=timeout,
            max_retries=2,
        )
        self.last_fetch_stats: dict[str, object] = {}

    def supports(self, bidql: dict[str, Any]) -> bool:
        return bidql.get("region", {}).get("scope") in {"global", "uk"}

    def collect(
        self, bidql: dict[str, Any], *, max_pages: int = 1, max_results: int = 10
    ) -> list[Notice]:
        terms = _source_terms(bidql)
        page_size = min(max(max_results * 4, 20), 100)
        next_url = build_search_url(self.api_url, bidql, limit=page_size)
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy) as fetcher:
            try:
                for _ in range(max_pages):
                    response = fetcher.get(next_url)
                    response.raise_for_status()
                    payload = response.json()
                    for notice in parse_ocds_notices(
                        payload, source_site=self.name, authority=self.authority
                    ):
                        if notice.id in seen or (terms and not _matches_terms(notice, terms)):
                            continue
                        seen.add(notice.id)
                        notices.append(notice)
                        if len(notices) >= max_results:
                            return notices
                    next_url = _safe_next_url(payload, self.api_url)
                    if not next_url:
                        break
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()
        return notices


class ContractsFinderAdapter(_UkOcdsAdapter):
    api_url = CONTRACTS_FINDER_API
    name = "contracts_finder"
    authority = "UK Cabinet Office - Contracts Finder"


class FindTenderAdapter(_UkOcdsAdapter):
    api_url = FIND_TENDER_API
    name = "find_tender"
    authority = "UK Cabinet Office - Find a Tender"


def _documents(release: dict[str, Any]) -> list[Attachment]:
    raw: list[object] = []
    tender = release.get("tender")
    if isinstance(tender, dict) and isinstance(tender.get("documents"), list):
        raw.extend(tender["documents"])
    for container_name in ("awards", "contracts"):
        containers = release.get(container_name)
        if not isinstance(containers, list):
            continue
        for container in containers:
            if isinstance(container, dict) and isinstance(container.get("documents"), list):
                raw.extend(container["documents"])
    documents: list[Attachment] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = _text(item.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        documents.append(
            Attachment(
                name=_text(item.get("title"))
                or _text(item.get("description"))
                or "OCDS document",
                url=url,
            )
        )
    return documents


def _delivery_region(tender: dict[str, Any]) -> str:
    values: list[str] = []
    items = tender.get("items")
    if not isinstance(items, list):
        return "United Kingdom"
    for item in items:
        addresses = item.get("deliveryAddresses") if isinstance(item, dict) else None
        if not isinstance(addresses, list):
            continue
        for address in addresses:
            if not isinstance(address, dict):
                continue
            for key in ("region", "locality", "countryName"):
                value = _text(address.get(key))
                if value and value not in values:
                    values.append(value)
    return ", ".join(values) or "United Kingdom"


def _buyer_name(release: dict[str, Any]) -> str:
    buyer = release.get("buyer")
    if isinstance(buyer, dict) and _text(buyer.get("name")):
        return _text(buyer.get("name"))
    parties = release.get("parties")
    if isinstance(parties, list):
        for party in parties:
            if not isinstance(party, dict):
                continue
            roles = _string_list(party.get("roles"))
            if "buyer" in roles:
                return _text(party.get("name"))
    return ""


def _award_value(release: dict[str, Any]) -> dict[str, Any]:
    awards = release.get("awards")
    if isinstance(awards, list):
        for award in awards:
            value = award.get("value") if isinstance(award, dict) else None
            if isinstance(value, dict):
                return value
    return {}


def _source_terms(bidql: dict[str, Any]) -> list[str]:
    values = bidql.get("topic", {}).get("source_terms") or []
    return [str(value).strip() for value in values if str(value).strip()]


def _matches_terms(notice: Notice, terms: list[str]) -> bool:
    haystack = " ".join(
        (
            notice.title,
            notice.content_text,
            _text(notice.fields.get("classification")),
        )
    ).casefold()
    return any(term.casefold() in haystack for term in terms)


def _safe_next_url(payload: object, api_url: str) -> str:
    links = payload.get("links") if isinstance(payload, dict) else None
    next_url = _text(links.get("next")) if isinstance(links, dict) else ""
    if not next_url:
        return ""
    expected = urlparse(api_url)
    candidate = urlparse(next_url)
    if candidate.scheme != "https" or candidate.netloc.casefold() != expected.netloc.casefold():
        return ""
    return urlunparse(candidate._replace(query=urlencode(parse_qsl(candidate.query))))


def _fallback_url(source_site: str) -> str:
    if source_site == "contracts_finder":
        return "https://www.contractsfinder.service.gov.uk/Search"
    return "https://www.find-tender.service.gov.uk/Search"


def _is_download(url: str) -> bool:
    path = urlparse(url).path.casefold()
    return path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _number_text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


def _text(value: object) -> str:
    return _clean_spaces(str(value or ""))
