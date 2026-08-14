from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from tendertrace.adapters.ccgp import CcgpAdapter, Notice
from tendertrace.adapters.ggzy import GgzyAdapter
from tendertrace.adapters.ted import TedAdapter
from tendertrace.adapters.worldbank import WorldBankAdapter
from tendertrace.config import Settings


class SourceAdapter(Protocol):
    name: str

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]: ...


@dataclass(frozen=True)
class SourceRunStat:
    source: str
    status: str
    count: int = 0
    error: str | None = None
    relaxed_city: bool = False
    fetch_stats: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "status": self.status,
            "count": self.count,
            "error": self.error,
            "relaxed_city": self.relaxed_city,
            "fetch_stats": self.fetch_stats or {},
        }


class MultiSourceAdapter:
    name = "multi"

    def __init__(self, adapters: list[SourceAdapter]) -> None:
        self.adapters = adapters
        self.last_source_stats: list[SourceRunStat] = []

    @classmethod
    def default(cls, settings: Settings) -> "MultiSourceAdapter":
        adapters: list[SourceAdapter] = [
            CcgpAdapter(),
            GgzyAdapter(),
            TedAdapter(),
            WorldBankAdapter(),
        ]
        try:
            from tendertrace.vault.qianlima import QianlimaAdapter, QianlimaSessionVault

            vault = QianlimaSessionVault(settings)
            if vault.has_storage_state():
                adapters.append(QianlimaAdapter(vault=vault))
        except ImportError:
            pass
        return cls(adapters)

    def collect(
        self,
        bidql: dict[str, Any],
        *,
        max_pages: int = 1,
        max_results: int = 10,
    ) -> list[Notice]:
        self.last_source_stats = []
        results_by_source: list[list[Notice]] = []
        seen: set[str] = set()
        for adapter in self.adapters:
            source_name = getattr(adapter, "name", adapter.__class__.__name__)
            supports = getattr(adapter, "supports", None)
            if callable(supports) and not supports(bidql):
                self.last_source_stats.append(
                    SourceRunStat(source=source_name, status="skipped")
                )
                results_by_source.append([])
                continue
            try:
                notices = adapter.collect(bidql, max_pages=max_pages, max_results=max_results)
                relaxed_city = False
                if not notices and _has_city_scope(bidql):
                    notices = adapter.collect(
                        _without_city_scope(bidql),
                        max_pages=max_pages,
                        max_results=max_results,
                    )
                    relaxed_city = bool(notices)
            except Exception as exc:
                self.last_source_stats.append(
                    SourceRunStat(
                        source=source_name,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                        fetch_stats=_fetch_stats(adapter),
                    )
                )
                results_by_source.append([])
                continue
            unique: list[Notice] = []
            for notice in notices:
                key = _notice_key(notice)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(notice)
            self.last_source_stats.append(
                SourceRunStat(
                    source=source_name,
                    status="finished",
                    count=len(unique),
                    relaxed_city=relaxed_city,
                    fetch_stats=_fetch_stats(adapter),
                )
            )
            results_by_source.append(unique)
        return _round_robin(results_by_source, max_results)


def _notice_key(notice: Notice) -> str:
    if notice.fields.get("cluster_key"):
        return str(notice.fields["cluster_key"])
    return f"{notice.source_site}:{notice.id}" if notice.id else notice.source_url


def _fetch_stats(adapter: SourceAdapter) -> dict[str, object]:
    stats = getattr(adapter, "last_fetch_stats", {})
    return stats if isinstance(stats, dict) else {}


def _round_robin(results_by_source: list[list[Notice]], limit: int) -> list[Notice]:
    merged: list[Notice] = []
    index = 0
    while len(merged) < limit:
        added = False
        for notices in results_by_source:
            if index < len(notices):
                merged.append(notices[index])
                added = True
                if len(merged) >= limit:
                    break
        if not added:
            break
        index += 1
    return merged


def _has_city_scope(bidql: dict[str, Any]) -> bool:
    region = bidql.get("region")
    return isinstance(region, dict) and bool(region.get("city"))


def _without_city_scope(bidql: dict[str, Any]) -> dict[str, Any]:
    relaxed = deepcopy(bidql)
    region = relaxed.get("region")
    if isinstance(region, dict):
        region["city"] = None
        region["city_adcode"] = None
        region["city_aliases"] = []
        region["relaxed_from_city"] = True
    meta = relaxed.setdefault("meta", {})
    if isinstance(meta, dict):
        meta["relaxed_city_scope"] = True
    return relaxed
