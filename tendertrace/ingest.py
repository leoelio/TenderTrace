from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from tendertrace.adapters.multi import MultiSourceAdapter
from tendertrace.adapters.ccgp import Notice
from tendertrace.config import Settings
from tendertrace.db import init_db
from tendertrace.intent import compile_intent
from tendertrace.pipeline.dedup import clean_and_cluster_notices
from tendertrace.runner import NoticeAdapter, persist_notices_and_clusters
from tendertrace.source_map import record_source_observations


@dataclass(frozen=True)
class IngestCycleResult:
    status: str
    query_count: int
    collected: int
    persisted: int
    topics: list[str]
    regions: list[str]
    source_stats: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_ingest_cycle(
    settings: Settings,
    *,
    topics: list[str] | tuple[str, ...] | None = None,
    regions: list[str] | tuple[str, ...] | None = None,
    now: datetime | None = None,
    window_days: int = 30,
    max_pages: int = 1,
    max_results: int = 20,
    adapter: NoticeAdapter | None = None,
) -> IngestCycleResult:
    init_db(settings)
    run_at = now or datetime.now().astimezone()
    topic_pool = list(topics or settings.ingest_topics)
    region_pool = list(regions or settings.ingest_regions)
    source_adapter = adapter or MultiSourceAdapter.default(settings)
    collected: list[Notice] = []
    source_stats: list[dict[str, object]] = []

    for region in region_pool:
        for topic in topic_pool:
            query = f"最近{window_days}天{region}{topic}招标信息"
            bidql = compile_intent(query, now=run_at)
            batch = source_adapter.collect(bidql, max_pages=max_pages, max_results=max_results)
            collected.extend(batch)
            source_stats.extend(
                {
                    **(item.to_dict() if hasattr(item, "to_dict") else item),
                    "region": region,
                    "topic": topic,
                }
                for item in getattr(source_adapter, "last_source_stats", [])
                if isinstance(item.to_dict() if hasattr(item, "to_dict") else item, dict)
            )

    deduped = clean_and_cluster_notices(collected).notices
    persist_notices_and_clusters(settings, deduped)
    record_source_observations(settings, source_stats)
    return IngestCycleResult(
        status="finished",
        query_count=len(topic_pool) * len(region_pool),
        collected=len(collected),
        persisted=len(deduped),
        topics=topic_pool,
        regions=region_pool,
        source_stats=source_stats,
    )
