from __future__ import annotations

from datetime import datetime
from typing import Any

from tendertrace.intent.region import parse_region
from tendertrace.intent.schedule import parse_schedule
from tendertrace.intent.time_expr import parse_time_expr, resolve_window
from tendertrace.intent.topic import extract_topic


def compile_intent(query: str, *, now: datetime | None = None) -> dict[str, Any]:
    parsed_time = parse_time_expr(query)
    parsed_schedule = parse_schedule(query)
    parsed_region = parse_region(_region_query(query, parsed_time.matched_text, parsed_schedule.matched_text))
    topic = extract_topic(
        query,
        region_text=parsed_region.matched_text,
        time_text=parsed_time.matched_text,
        schedule_text=parsed_schedule.matched_text,
    )
    clarify_needed: list[str] = []
    topic_confidence = float(topic.get("confidence") or 0.0)
    if topic_confidence < 0.65 and not topic.get("open_scope"):
        clarify_needed.append("topic")
    if not parsed_region.value["province"] and parsed_region.value.get("scope") not in {
        "global",
        "eu",
        "worldbank",
        "uk",
        "idb",
        "adb",
    }:
        clarify_needed.append("region")

    confidence = {
        "topic": topic_confidence if topic["core"] else 0.8 if topic.get("open_scope") else 0.0,
        "region": (
            1.0
            if parsed_region.value["province"]
            or parsed_region.value.get("scope")
            in {"global", "eu", "worldbank", "uk", "idb", "adb"}
            else 0.0
        ),
        "time": 0.96 if parsed_time.value.get("origin") == "rule" else 0.65,
        "schedule": 0.98,
    }
    bidql = {
        "version": "1.0",
        "query": query,
        "topic": topic,
        "region": parsed_region.value,
        "time": parsed_time.value,
        "schedule": parsed_schedule.value,
        "delivery": {"format": "docx", "channels": ["web", "outbox"]},
        "meta": {
            "confidence": confidence,
            "channel_agreement": None,
            "channels": ["rule"],
            "clarify_needed": clarify_needed,
            "clarification_questions": _clarification_questions(clarify_needed, topic),
        },
    }
    if now is not None:
        bidql["time"]["resolved_window"] = resolve_window(parsed_time.value, now)
    return bidql


def _region_query(query: str, time_text: str, schedule_text: str) -> str:
    text = query
    for removable in (time_text, schedule_text):
        if removable:
            text = text.replace(removable, " ")
    return text


def _clarification_questions(clarify_needed: list[str], topic: dict[str, Any]) -> list[dict[str, object]]:
    questions: list[dict[str, object]] = []
    if "topic" in clarify_needed:
        candidates = topic.get("core") if isinstance(topic.get("core"), list) else []
        questions.append(
            {
                "field": "topic",
                "question": "我不确定要检索的采购品类，请补充或确认主题关键词。",
                "candidates": candidates,
            }
        )
    if "region" in clarify_needed:
        questions.append(
            {
                "field": "region",
                "question": "我没有识别到明确地区，请补充省、市或区县。",
                "candidates": [],
            }
        )
    return questions
