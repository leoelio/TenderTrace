from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty
from typing import Any, Iterable
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


@dataclass(frozen=True)
class GoldCoverageResult:
    available: bool
    complete: bool
    gold_path: str
    case_count: int
    annotated_case_count: int
    empty_case_count: int
    expected_total: int
    annotation_completion: float
    cases: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_gold_coverage(
    settings: Settings,
    *,
    gold_path: Path | None = None,
) -> GoldCoverageResult:
    path = _resolve_gold_path(settings, gold_path)
    cases = _load_cases(path)
    items: list[dict[str, Any]] = []
    annotated_count = 0
    expected_total = 0

    for case in cases:
        expected_count = len(_expected_groups(case))
        expected_total += expected_count
        if expected_count:
            annotated_count += 1
            status = "ready"
        else:
            status = "needs_annotation"
        items.append(
            {
                "id": case.get("id"),
                "query": case.get("query"),
                "status": status,
                "expected_count": expected_count,
            }
        )

    empty_count = len(cases) - annotated_count
    return GoldCoverageResult(
        available=annotated_count > 0,
        complete=bool(cases) and empty_count == 0,
        gold_path=str(path),
        case_count=len(cases),
        annotated_case_count=annotated_count,
        empty_case_count=empty_count,
        expected_total=expected_total,
        annotation_completion=_ratio(annotated_count, len(cases)),
        cases=items,
    )


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
    case_ids: Iterable[str] | None = None,
    case_timeout_seconds: int | None = None,
    existing_payload: dict[str, Any] | None = None,
    adapter: Any | None = None,
) -> dict[str, Any]:
    path = _resolve_gold_path(settings, gold_path)
    cases = _load_cases(path)
    selected_ids = {str(item) for item in case_ids or [] if str(item).strip()}
    existing_by_id = _existing_candidate_items(existing_payload)
    items = []
    for case in cases:
        case_id = str(case.get("id") or "")
        if selected_ids and case_id not in selected_ids:
            continue
        if case_id in existing_by_id and existing_by_id[case_id].get("status") == "finished":
            cached = dict(existing_by_id[case_id])
            cached["cached"] = True
            items.append(cached)
            continue
        items.append(
            _collect_case_with_timeout(
                settings,
                case,
                max_pages=max_pages,
                max_results=max_results,
                timeout_seconds=case_timeout_seconds,
                adapter=adapter,
            )
        )
    return {
        "gold_path": str(path),
        "case_count": len(cases),
        "selected_case_count": len(items),
        "max_pages": max_pages,
        "max_results": max_results,
        "case_timeout_seconds": case_timeout_seconds,
        "items": items,
    }


def _collect_case_with_timeout(
    settings: Settings,
    case: dict[str, Any],
    *,
    max_pages: int,
    max_results: int,
    timeout_seconds: int | None,
    adapter: Any | None = None,
) -> dict[str, Any]:
    if adapter is not None or not timeout_seconds or timeout_seconds <= 0:
        return _collect_case(settings, case, max_pages=max_pages, max_results=max_results, adapter=adapter)

    queue: Queue = Queue()
    process = Process(
        target=_collect_case_worker,
        args=(str(settings.workspace_root), case, max_pages, max_results, queue),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        return _case_error(case, "timeout", f"case exceeded {timeout_seconds}s")
    try:
        payload = queue.get_nowait()
    except Empty:
        return _case_error(case, "failed", f"worker exited with code {process.exitcode}")
    if payload.get("status") == "ok" and isinstance(payload.get("item"), dict):
        return payload["item"]
    return _case_error(case, "failed", str(payload.get("error") or "unknown worker error"))


def _collect_case_worker(
    workspace_root: str,
    case: dict[str, Any],
    max_pages: int,
    max_results: int,
    queue: Queue,
) -> None:
    try:
        settings = Settings.load(Path(workspace_root))
        item = _collect_case(settings, case, max_pages=max_pages, max_results=max_results)
    except Exception as exc:
        queue.put({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        return
    queue.put({"status": "ok", "item": item})


def _collect_case(
    settings: Settings,
    case: dict[str, Any],
    *,
    max_pages: int,
    max_results: int,
    adapter: Any | None = None,
) -> dict[str, Any]:
    try:
        bidql = compile_intent(str(case["query"]), now=_case_now(case))
        collector = adapter or MultiSourceAdapter.default(settings)
        collected = collector.collect(bidql, max_pages=max_pages, max_results=max_results)
        deduped = clean_and_cluster_notices(collected).notices
        return {
            "id": case.get("id"),
            "query": case.get("query"),
            "status": "finished",
            "candidate_count": len(deduped),
            "source_stats": _source_stats(collector),
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
    except Exception as exc:
        return _case_error(case, "failed", f"{type(exc).__name__}: {exc}")


def _case_error(case: dict[str, Any], status: str, error: str) -> dict[str, Any]:
    return {
        "id": case.get("id"),
        "query": case.get("query"),
        "status": status,
        "error": error,
        "candidate_count": 0,
        "source_stats": [],
        "candidates": [],
    }


def _source_stats(adapter: Any) -> list[dict[str, Any]]:
    stats = getattr(adapter, "last_source_stats", [])
    return [item.to_dict() if hasattr(item, "to_dict") else item for item in stats]


def _existing_candidate_items(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    items = payload.get("items")
    if not isinstance(items, list):
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = item
    return by_id


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
