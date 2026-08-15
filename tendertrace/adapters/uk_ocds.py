from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunparse

from selectolax.parser import HTMLParser

from tendertrace.adapters.ccgp import Attachment, Notice, _clean_spaces
from tendertrace.fetching import FetchPolicy, ManagedFetcher


CONTRACTS_FINDER_API = (
    "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
)
FIND_TENDER_API = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
CONTRACTS_FINDER_SEARCH = "https://www.contractsfinder.service.gov.uk/Search"
FIND_TENDER_SEARCH = "https://www.find-tender.service.gov.uk/Search/Results"


@dataclass(frozen=True)
class SearchCandidate:
    notice_id: str
    title: str
    source_url: str
    publish_time: str
    purchaser: str
    region: str
    content_text: str
    fields: dict[str, str]


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
    search_url = ""
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
        if not terms:
            return []
        notices: list[Notice] = []
        seen: set[str] = set()
        with ManagedFetcher(self.policy) as fetcher:
            try:
                candidates = _discover_candidates(
                    fetcher,
                    search_url=self.search_url,
                    source_site=self.name,
                    terms=terms,
                    bidql=bidql,
                    max_pages=max_pages,
                    limit=max_results,
                )
                parsed = [
                    _candidate_notice(
                        item,
                        source_site=self.name,
                        authority=self.authority,
                    )
                    for item in candidates
                ]
                for notice in parsed:
                    if notice.id in seen or not _in_window(notice.publish_time, bidql):
                        continue
                    seen.add(notice.id)
                    notices.append(notice)
                    if len(notices) >= max_results:
                        break
            finally:
                self.last_fetch_stats = fetcher.stats.to_dict()
        return notices


class ContractsFinderAdapter(_UkOcdsAdapter):
    api_url = CONTRACTS_FINDER_API
    search_url = CONTRACTS_FINDER_SEARCH
    name = "contracts_finder"
    authority = "UK Cabinet Office - Contracts Finder"


class FindTenderAdapter(_UkOcdsAdapter):
    api_url = FIND_TENDER_API
    search_url = FIND_TENDER_SEARCH
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


def parse_search_candidates(html: str, *, source_site: str) -> list[SearchCandidate]:
    parser = HTMLParser(html)
    candidates: list[SearchCandidate] = []
    seen: set[str] = set()
    for row in parser.css(".search-result"):
        anchor = row.css_first(".search-result-header a[href]")
        if anchor is None:
            continue
        source_url = _canonical_notice_url(anchor.attributes.get("href", ""), source_site)
        notice_id = _notice_id(source_url, source_site)
        title = _text(anchor.text(separator=" ", strip=True))
        if not notice_id or not title or notice_id in seen:
            continue
        seen.add(notice_id)
        fields: dict[str, str] = {}
        for entry in row.css(".search-result-entry"):
            label_node = entry.css_first("strong")
            if label_node is None:
                continue
            label = _text(label_node.text(separator=" ", strip=True))
            full_text = _text(entry.text(separator=" ", strip=True))
            value = full_text[len(label) :].strip() if full_text.startswith(label) else full_text
            if label and value:
                fields[label] = value
        purchaser_node = row.css_first(".search-result-sub-header")
        purchaser = (
            _text(purchaser_node.text(separator=" ", strip=True)) if purchaser_node else ""
        )
        content = " | ".join(f"{key}: {value}" for key, value in fields.items())
        candidates.append(
            SearchCandidate(
                notice_id=notice_id,
                title=title,
                source_url=source_url,
                publish_time=_english_date(fields.get("Publication date", "")),
                purchaser=purchaser,
                region=fields.get("Contract location", "")
                or fields.get("Contract locations", "")
                or "United Kingdom",
                content_text=content,
                fields={
                    "deadline": fields.get("Closing", "")
                    or fields.get("Closing date", ""),
                    "estimated_value": fields.get("Contract value", "")
                    or fields.get("Contract value excluding VAT", "")
                    or fields.get("Total value excluding VAT", ""),
                    "notice_status": fields.get("Notice status", ""),
                    "procurement_stage": fields.get("Procurement stage", "")
                    or fields.get("Notice type", ""),
                },
            )
        )
    return candidates


def build_search_form(html: str, *, term: str, bidql: dict[str, Any]) -> dict[str, str]:
    parser = HTMLParser(html)
    form = parser.css_first("#search_form")
    if form is None:
        return {}
    payload: dict[str, str] = {}
    available: set[str] = set()
    for node in form.css("input[name]"):
        name = _text(node.attributes.get("name"))
        if not name:
            continue
        available.add(name)
        input_type = _text(node.attributes.get("type")).casefold()
        if input_type == "hidden" or "checked" in node.attributes:
            payload[name] = _text(node.attributes.get("value"))
    payload["keywords"] = term
    payload["adv_search"] = ""
    if "open" in available:
        payload["open"] = "1"
    window = bidql.get("time", {}).get("resolved_window")
    if isinstance(window, dict):
        _set_form_date(payload, available, "published_from", _text(window.get("from")))
        _set_form_date(payload, available, "published_to", _text(window.get("to")))
    return payload


def _discover_candidates(
    fetcher: ManagedFetcher,
    *,
    search_url: str,
    source_site: str,
    terms: list[str],
    bidql: dict[str, Any],
    max_pages: int,
    limit: int,
) -> list[SearchCandidate]:
    for term in terms[:2]:
        first = fetcher.get(search_url)
        first.raise_for_status()
        payload = build_search_form(first.text, term=term, bidql=bidql)
        if not payload.get("keywords") or not payload.get("form_token"):
            raise RuntimeError(f"{source_site} public search form is unavailable")
        response = fetcher.post(search_url, data=payload)
        response.raise_for_status()
        candidates: list[SearchCandidate] = []
        seen: set[str] = set()
        for _ in range(max(1, max_pages)):
            for candidate in parse_search_candidates(response.text, source_site=source_site):
                if candidate.notice_id in seen:
                    continue
                seen.add(candidate.notice_id)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates
            next_url = _next_search_page(response.text, search_url)
            if not next_url:
                break
            response = fetcher.get(next_url)
            response.raise_for_status()
        if candidates:
            return candidates
    return []


def _candidate_notice(
    candidate: SearchCandidate, *, source_site: str, authority: str
) -> Notice:
    fields = dict(candidate.fields)
    fields.update(
        {
            "cluster_key": f"{source_site}:{candidate.notice_id}",
            "authority": authority,
        }
    )
    return Notice(
        id=candidate.notice_id,
        source_site=source_site,
        title=candidate.title,
        publish_time=candidate.publish_time,
        region=candidate.region,
        purchaser=candidate.purchaser,
        source_url=candidate.source_url,
        content_text=candidate.content_text,
        core_content=(candidate.content_text or candidate.title)[:600],
        fields=fields,
    )


def _set_form_date(
    payload: dict[str, str], available: set[str], prefix: str, value: str
) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return
    values = {"day": str(parsed.day), "month": str(parsed.month), "year": str(parsed.year)}
    for part, item in values.items():
        name = f"{prefix}[{part}]"
        if name in available:
            payload[name] = item


def _canonical_notice_url(value: str, source_site: str) -> str:
    base = CONTRACTS_FINDER_SEARCH if source_site == "contracts_finder" else FIND_TENDER_SEARCH
    parsed = urlsplit(urljoin(base, value))
    expected_host = urlparse(base).netloc.casefold()
    if parsed.scheme != "https" or parsed.netloc.casefold() != expected_host:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _notice_id(source_url: str, source_site: str) -> str:
    path = urlparse(source_url).path.rstrip("/")
    value = path.rsplit("/", 1)[-1]
    if source_site == "contracts_finder":
        parts = value.split("-")
        return value.casefold() if len(parts) == 5 and len(value) == 36 else ""
    year_parts = value.split("-")
    return value if len(year_parts) == 2 and all(part.isdigit() for part in year_parts) else ""


def _english_date(value: str) -> str:
    matched = re.search(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", value)
    candidate = matched.group(0) if matched else value.strip()
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return value[:10]


def _next_search_page(html: str, search_url: str) -> str:
    parser = HTMLParser(html)
    node = parser.css_first("a.standard-paginate-next[href]")
    if node is None:
        return ""
    candidate = urlparse(urljoin(search_url, node.attributes.get("href", "")))
    expected = urlparse(search_url)
    if candidate.scheme != "https" or candidate.netloc.casefold() != expected.netloc.casefold():
        return ""
    if not candidate.path.casefold().startswith("/search"):
        return ""
    return urlunparse(candidate._replace(fragment=""))


def _in_window(publish_time: str, bidql: dict[str, Any]) -> bool:
    window = bidql.get("time", {}).get("resolved_window")
    if not isinstance(window, dict) or not window.get("from") or not window.get("to"):
        return True
    return str(window["from"]) <= publish_time[:10] <= str(window["to"])


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
