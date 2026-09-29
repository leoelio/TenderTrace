from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps


VIEWPORT_PROFILES = {
    "projector_1440": (1440, 900),
    "full_hd_1920": (1920, 1080),
}

REQUIRED_BOOLEAN_CHECKS = (
    "state_words_with_symbols",
    "conclusion_titles_visible",
    "identity_consistent",
    "focus_visible",
    "motion_can_be_disabled",
    "presentation_preserves_content",
    "editors_hidden_in_presentation",
)


def record_visual_system_audit(
    settings: Settings,
    *,
    profile: object,
    viewport_width: object,
    viewport_height: object,
    notice_id: object,
    scroll_width: object,
    critical_overflows: object,
    checks: object,
    user_agent: object = "",
) -> dict[str, object]:
    init_db(settings)
    profile_text = str(profile or "").strip()
    if profile_text not in VIEWPORT_PROFILES:
        raise ValueError(f"profile must be one of: {', '.join(VIEWPORT_PROFILES)}")
    width = _bounded_int(viewport_width, "viewport_width", 320, 7680)
    height = _bounded_int(viewport_height, "viewport_height", 320, 4320)
    if (width, height) != VIEWPORT_PROFILES[profile_text]:
        raise ValueError("viewport dimensions do not match the selected profile")
    notice_text = _controlled_text(notice_id, "notice_id", 180)
    measured_scroll = _bounded_int(scroll_width, "scroll_width", 0, 20000)
    overflows = [str(item)[:160] for item in critical_overflows] if isinstance(critical_overflows, list) else []
    check_values = dict(checks) if isinstance(checks, dict) else {}
    normalized_checks = {
        key: bool(check_values.get(key))
        for key in REQUIRED_BOOLEAN_CHECKS
    }
    normalized_checks.update(
        {
            "min_status_font_px": _bounded_number(
                check_values.get("min_status_font_px"), "min_status_font_px", 0, 200
            ),
            "critical_component_count": _bounded_int(
                check_values.get("critical_component_count"),
                "critical_component_count",
                0,
                100,
            ),
            "conclusion_title_count": _bounded_int(
                check_values.get("conclusion_title_count"),
                "conclusion_title_count",
                0,
                100,
            ),
            "focus_target_found": bool(check_values.get("focus_target_found")),
            "focus_rule_count": _bounded_int(
                check_values.get("focus_rule_count", 0), "focus_rule_count", 0, 100
            ),
            "focus_outline_px": _bounded_number(
                check_values.get("focus_outline_px", 0), "focus_outline_px", 0, 100
            ),
        }
    )
    passed = (
        measured_scroll <= width
        and not overflows
        and all(normalized_checks[key] for key in REQUIRED_BOOLEAN_CHECKS)
        and float(normalized_checks["min_status_font_px"]) >= 16
        and int(normalized_checks["critical_component_count"]) >= 4
        and int(normalized_checks["conclusion_title_count"]) >= 4
        and bool(str(user_agent or "").strip())
    )
    audit_id = str(uuid4())
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO visual_system_audits(
                id, profile, viewport_width, viewport_height, notice_id,
                scroll_width, critical_overflows_json, checks_json, status, user_agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                profile_text,
                width,
                height,
                notice_text,
                measured_scroll,
                json_dumps(overflows),
                json_dumps(normalized_checks),
                "passed" if passed else "failed",
                _controlled_text(user_agent, "user_agent", 300, required=False),
            ),
        )
    return {
        "id": audit_id,
        "profile": profile_text,
        "viewport_width": width,
        "viewport_height": height,
        "notice_id": notice_text,
        "scroll_width": measured_scroll,
        "critical_overflows": overflows,
        "checks": normalized_checks,
        "status": "passed" if passed else "failed",
        "measurement": "same_origin_browser_dom",
    }


def visual_system_overview(settings: Settings) -> dict[str, object]:
    init_db(settings)
    audits = list_visual_system_audits(settings)
    passed = sum(item["status"] == "passed" for item in audits)
    return {
        "status": "ready" if passed == len(VIEWPORT_PROFILES) else "attention",
        "audits": audits,
        "summary": {
            "profiles_required": len(VIEWPORT_PROFILES),
            "profiles_passed": passed,
            "all_profiles_passed": passed == len(VIEWPORT_PROFILES),
        },
        "state_language": [
            {"key": "verified", "symbol": "✓", "label": "有据满足"},
            {"key": "review", "symbol": "!", "label": "待确认"},
            {"key": "gap", "symbol": "×", "label": "缺口或失效"},
            {"key": "system", "symbol": "i", "label": "系统信息"},
            {"key": "human", "symbol": "人", "label": "人工裁决"},
        ],
        "motion": {
            "productive_ms": 320,
            "expressive_ms": 480,
            "can_disable": True,
            "respects_reduced_motion": True,
        },
    }


def list_visual_system_audits(settings: Settings) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    with connection(settings) as conn:
        for profile, (width, height) in VIEWPORT_PROFILES.items():
            row = conn.execute(
                """
                SELECT * FROM visual_system_audits
                WHERE profile = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (profile,),
            ).fetchone()
            items.append(
                {
                    "profile": profile,
                    "viewport_width": width,
                    "viewport_height": height,
                    "notice_id": str(row["notice_id"]) if row else "",
                    "scroll_width": int(row["scroll_width"] or 0) if row else 0,
                    "critical_overflows": _json_list(row["critical_overflows_json"]) if row else [],
                    "checks": _json_object(row["checks_json"]) if row else {},
                    "status": str(row["status"]) if row else "not_checked",
                    "measurement": "same_origin_browser_dom" if row else "",
                    "user_agent_present": bool(str(row["user_agent"] or "")) if row else False,
                    "created_at": str(row["created_at"]) if row else "",
                }
            )
    return items


def _json_list(value: Any) -> list[Any]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _controlled_text(value: object, field: str, max_length: int, *, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return number


def _bounded_number(value: object, field: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return round(number, 2)
