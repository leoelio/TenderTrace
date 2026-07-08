from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import re
from typing import Any

from tendertrace.config import Settings
from tendertrace.llm.audit import record_model_audit
from tendertrace.llm.gateway import ModelCallResult, ModelGateway, model_status


@dataclass(frozen=True)
class ModelEnhancement:
    bidql: dict[str, Any]
    result: ModelCallResult
    applied_keywords: list[str]
    applied_negatives: list[str]


def enhance_bidql_with_model(
    settings: Settings,
    bidql: dict[str, Any],
    *,
    run_id: str | None = None,
    gateway: ModelGateway | None = None,
) -> ModelEnhancement:
    prompt = _prompt_for_bidql(bidql)
    model_gateway = gateway or ModelGateway(settings)
    result = model_gateway.generate_json(
        system=_SYSTEM_PROMPT,
        user=prompt,
    )
    if run_id:
        record_model_audit(settings, run_id=run_id, result=result, prompt_text=prompt)
    if result.status != "ok" or not isinstance(result.parsed, dict):
        return ModelEnhancement(
            bidql=_attach_meta(deepcopy(bidql), result, [], []),
            result=result,
            applied_keywords=[],
            applied_negatives=[],
        )
    enhanced = deepcopy(bidql)
    topic = enhanced.setdefault("topic", {})
    if not isinstance(topic, dict):
        enhanced["topic"] = topic = {}
    blocked_terms = _negative_terms(topic) | set(_safe_terms(result.parsed.get("negative_keywords"), set()))
    applied_keywords = _apply_expanded_keywords(
        topic,
        result.parsed.get("expanded_keywords"),
        blocked_terms=blocked_terms,
    )
    applied_negatives = _apply_negative_keywords(topic, result.parsed.get("negative_keywords"))
    return ModelEnhancement(
        bidql=_attach_meta(enhanced, result, applied_keywords, applied_negatives),
        result=result,
        applied_keywords=applied_keywords,
        applied_negatives=applied_negatives,
    )


def skipped_model_enhancement(settings: Settings, bidql: dict[str, Any]) -> ModelEnhancement:
    status = model_status(settings)
    result = ModelCallResult(
        mode=status.mode,
        provider=status.provider,
        model=status.model,
        status="skipped",
        error="model enhancement disabled",
    )
    return ModelEnhancement(
        bidql=_attach_meta(deepcopy(bidql), result, [], []),
        result=result,
        applied_keywords=[],
        applied_negatives=[],
    )


_SYSTEM_PROMPT = """You enhance a tender-search BidQL object.
Return one strict JSON object only:
{"expanded_keywords":[],"negative_keywords":[],"intent_summary":"","confidence":0.0}
Rules:
- Preserve the original region, dates, schedule, delivery and core keyword.
- expanded_keywords are conservative synonyms or procurement-domain variants.
- negative_keywords are terms that indicate result notices, failures or unrelated content.
- Do not include URLs, markdown or explanations.
- Use the same language as the query when possible.
"""


def _prompt_for_bidql(bidql: dict[str, Any]) -> str:
    payload = {
        "query": bidql.get("query"),
        "topic": bidql.get("topic"),
        "region": bidql.get("region"),
        "time": bidql.get("time"),
        "schedule": bidql.get("schedule"),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _apply_expanded_keywords(
    topic: dict[str, Any],
    value: object,
    *,
    blocked_terms: set[str] | None = None,
) -> list[str]:
    existing = _existing_terms(topic)
    terms = _safe_terms(value, existing, blocked_terms=blocked_terms or set())
    if not terms:
        return []
    expanded = topic.get("expanded")
    if not isinstance(expanded, list):
        expanded = []
        topic["expanded"] = expanded
    for term in terms:
        expanded.append({"term": term, "weight": 0.72, "origin": "model"})
    return terms


def _apply_negative_keywords(topic: dict[str, Any], value: object) -> list[str]:
    negative = topic.get("negative")
    if not isinstance(negative, list):
        negative = []
        topic["negative"] = negative
    existing = {str(item).strip() for item in negative if str(item).strip()}
    terms = _safe_terms(value, existing)
    negative.extend(terms)
    return terms


def _negative_terms(topic: dict[str, Any]) -> set[str]:
    negative = topic.get("negative")
    if not isinstance(negative, list):
        return set()
    return {str(item).strip() for item in negative if str(item).strip()}


def _existing_terms(topic: dict[str, Any]) -> set[str]:
    terms = {str(item).strip() for item in topic.get("core", []) if str(item).strip()}
    expanded = topic.get("expanded")
    if isinstance(expanded, list):
        for item in expanded:
            if isinstance(item, dict):
                term = str(item.get("term") or "").strip()
            else:
                term = str(item).strip()
            if term:
                terms.add(term)
    negative = topic.get("negative")
    if isinstance(negative, list):
        terms.update(str(item).strip() for item in negative if str(item).strip())
    return terms


def _safe_terms(
    value: object,
    existing: set[str],
    *,
    blocked_terms: set[str] | None = None,
) -> list[str]:
    if not isinstance(value, list):
        return []
    accepted: list[str] = []
    seen = set(existing)
    blocked = {term for term in (blocked_terms or set()) if term}
    for item in value:
        term = str(item).strip()
        if not _is_safe_term(term):
            continue
        if any(blocked_term in term for blocked_term in blocked):
            continue
        if term in seen:
            continue
        accepted.append(term)
        seen.add(term)
        if len(accepted) >= 8:
            break
    return accepted


def _is_safe_term(term: str) -> bool:
    if not 1 < len(term) <= 32:
        return False
    if "\n" in term or "\r" in term or "\t" in term:
        return False
    if re.search(r"https?://|www\.|[{}<>]", term, re.IGNORECASE):
        return False
    return True


def _attach_meta(
    bidql: dict[str, Any],
    result: ModelCallResult,
    applied_keywords: list[str],
    applied_negatives: list[str],
) -> dict[str, Any]:
    meta = bidql.setdefault("meta", {})
    if not isinstance(meta, dict):
        bidql["meta"] = meta = {}
    channels = meta.get("channels")
    if isinstance(channels, list) and result.status == "ok" and (
        applied_keywords or applied_negatives
    ):
        if "model" not in channels:
            channels.append("model")
    meta["model_enhancement"] = {
        **result.safe_dict(),
        "applied_keywords": applied_keywords,
        "applied_negatives": applied_negatives,
        "intent_summary": str((result.parsed or {}).get("intent_summary") or "")
        if isinstance(result.parsed, dict)
        else "",
        "confidence": (result.parsed or {}).get("confidence")
        if isinstance(result.parsed, dict)
        else None,
    }
    return bidql
