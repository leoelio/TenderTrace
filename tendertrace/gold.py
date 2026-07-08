from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tendertrace.adapters.multi import MultiSourceAdapter
from tendertrace.config import Settings
from tendertrace.intent import compile_intent
from tendertrace.pipeline.dedup import canonicalize_url, clean_and_cluster_notices, normalize_title
from tendertrace.retrieval import search_notices


DEFAULT_GOLD_PATH = Path("docs/evaluation/gold_benchmark.json")


@dataclass(frozen=True)
class GoldEvaluationResult:
    available: bool
    gold_path: str
    case_count: int
    annotated_case_count: int
    expected_total: int
    recall_at: dict[str, float]
    precision_at: dict[str, float]
    cases: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_gold_recall(
    settings: Settings,
    *,
    gold_path: Path | None = None,
    k_values: tuple[int, ...] = (5, 10),
) -> GoldEvaluationResult:
    path = _resolve_gold_path(settings, gold_path)
    cases = _load_cases(path)
    max_k = max(k_values)
    evaluated: list[dict[str, Any]] = []
    totals = {k: {"hits": 0, "expected": 0, "retrieved": 0} for k in k_values}
    annotated_count = 0

    for case in cases:
        expected = _expected_groups(case)
        if not expected:
            evaluated.append(_pending_case(case))
            continue
        annotated_count += 1
        bidql = compile_intent(str(case["query"]), now=_case_now(case))
        retrieved = search_notices(settings, bidql, max_results=max_k).notices
        retrieved_keys = [_notice_match_keys(item) for item in retrieved]
        case_result = {
            "id": case.get("id"),
            "query": case.get("query"),
            "status": "evaluated",
            "expected_count": len(expected),
            "retrieved_count": len(retrieved),
            "recall_at": {},
            "precision_at": {},
            "missed": _missed_expected(expected, retrieved_keys),
        }
        for k in k_values:
            sliced = retrieved_keys[:k]
            hits = _hit_count(expected, sliced)
            totals[k]["hits"] += hits
            totals[k]["expected"] += len(expected)
            totals[k]["retrieved"] += min(k, len(retrieved))
            case_result["recall_at"][str(k)] = _ratio(hits, len(expected))
            case_result["precision_at"][str(k)] = _ratio(hits, min(k, len(retrieved)))
        evaluated.append(case_result)

    expected_total = sum(item["expected"] for item in totals.values()) // max(1, len(k_values))
    return GoldEvaluationResult(
        available=annotated_count > 0,
        gold_path=str(path),
        case_count=len(cases),
        annotated_case_count=annotated_count,
        expected_total=expected_total,
        recall_at={str(k): _ratio(totals[k]["hits"], totals[k]["expected"]) for k in k_values},
        precision_at={str(k): _ratio(totals[k]["hits"], totals[k]["retrieved"]) for k in k_values},
        cases=evaluated,
    )


def build_gold_candidates(
    settings: Settings,
    *,
    gold_path: Path | None = None,
    max_pages: int = 1,
    max_results: int = 20,
) -> dict[str, Any]:
    path = _resolve_gold_path(settings, gold_path)
    cases = _load_cases(path)
    adapter = MultiSourceAdapter.default(settings)
    items = []
    for case in cases:
        bidql = compile_intent(str(case["query"]), now=_case_now(case))
        collected = adapter.collect(bidql, max_pages=max_pages, max_results=max_results)
        deduped = clean_and_cluster_notices(collected).notices
        items.append(
            {
                "id": case.get("id"),
                "query": case.get("query"),
                "candidates": [
                    {
                        "source_site": notice.source_site,
                        "notice_id": notice.id,
                        "title": notice.title,
                        "publish_time": notice.publish_time,
                        "source_url": notice.source_url,
                        "match_keys": sorted(_notice_match_keys(notice)),
                    }
                    for notice in deduped
                ],
            }
        )
    return {
        "gold_path": str(path),
        "case_count": len(cases),
        "max_pages": max_pages,
        "max_results": max_results,
        "items": items,
    }


def _resolve_gold_path(settings: Settings, gold_path: Path | None) -> Path:
    path = gold_path or DEFAULT_GOLD_PATH
    if not path.is_absolute():
        path = settings.workspace_root / path
    return path


def _load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    return [case for case in cases if isinstance(case, dict) and case.get("query")]


def _case_now(case: dict[str, Any]) -> datetime | None:
    raw = case.get("now")
    if raw:
        return datetime.fromisoformat(str(raw))
    return datetime(2026, 7, 8, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


def _expected_groups(case: dict[str, Any]) -> list[set[str]]:
    notices = case.get("gold_notices") or case.get("expected_notices") or []
    if not isinstance(notices, list):
        return []
    groups: list[set[str]] = []
    for item in notices:
        if isinstance(item, str):
            keys = {_key_from_url_or_text(item)}
        elif isinstance(item, dict):
            keys = _gold_notice_keys(item)
        else:
            keys = set()
        keys = {key for key in keys if key}
        if keys:
            groups.append(keys)
    return groups


def _gold_notice_keys(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    source_site = str(item.get("source_site") or "").strip()
    notice_id = str(item.get("notice_id") or item.get("id") or "").strip()
    source_url = str(item.get("source_url") or item.get("url") or "").strip()
    title = str(item.get("title") or "").strip()
    if source_site and notice_id:
        keys.add(f"id:{source_site}:{notice_id}")
    if source_url:
        keys.add(_key_from_url_or_text(source_url))
    if title:
        keys.add(f"title:{normalize_title(title)}")
    return keys


def _notice_match_keys(notice) -> set[str]:
    keys = set()
    if notice.source_site and notice.id:
        keys.add(f"id:{notice.source_site}:{notice.id}")
    if notice.source_url:
        keys.add(_key_from_url_or_text(notice.source_url))
    if notice.title:
        keys.add(f"title:{normalize_title(notice.title)}")
    return keys


def _key_from_url_or_text(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return f"url:{canonicalize_url(value)}"
    return value


def _hit_count(expected: list[set[str]], retrieved_keys: list[set[str]]) -> int:
    hits = 0
    matched_indexes: set[int] = set()
    for retrieved in retrieved_keys:
        for index, expected_keys in enumerate(expected):
            if index in matched_indexes:
                continue
            if expected_keys & retrieved:
                hits += 1
                matched_indexes.add(index)
                break
    return hits


def _missed_expected(expected: list[set[str]], retrieved_keys: list[set[str]]) -> list[str]:
    retrieved_union = set().union(*retrieved_keys) if retrieved_keys else set()
    return [
        sorted(keys)[0]
        for keys in expected
        if not (keys & retrieved_union)
    ]


def _pending_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case.get("id"),
        "query": case.get("query"),
        "status": "needs_annotation",
        "expected_count": 0,
        "retrieved_count": 0,
        "recall_at": {},
        "precision_at": {},
        "missed": [],
    }


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 3)
