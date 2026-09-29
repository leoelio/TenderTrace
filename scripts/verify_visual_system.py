from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
from urllib.request import urlopen


BASE_URL = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/demo/visual_system_acceptance_20260928.json"


def request_json(path: str) -> dict[str, object]:
    with urlopen(f"{BASE_URL}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def request_text(path: str) -> tuple[int, str]:
    with urlopen(f"{BASE_URL}{path}", timeout=30) as response:
        return response.status, response.read().decode("utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    health = request_json("/api/health")
    visual = request_json("/api/visual-system")
    reliability = request_json("/api/demo-reliability")
    page_status, page = request_text("/?view=demoConsoleView")
    _, javascript = request_text("/app.js")
    _, stylesheet = request_text("/styles.css")
    audits = list(visual.get("audits") or [])
    main_case = next(
        (item for item in reliability.get("cases") or [] if item.get("role") == "main"),
        {},
    )
    environment = dict(reliability.get("environment") or {})
    environment_checks = {
        str(item.get("key") or ""): item for item in environment.get("checks") or []
    }
    required_checks = (
        "state_words_with_symbols",
        "conclusion_titles_visible",
        "identity_consistent",
        "focus_visible",
        "motion_can_be_disabled",
        "presentation_preserves_content",
        "editors_hidden_in_presentation",
    )
    checks = {
        "service_healthy": health.get("status") == "ok",
        "schema_version_52_active": 52
        in ((health.get("database") or {}).get("schema_versions") or []),
        "direct_page_http_200": page_status == 200,
        "visual_controls_present": 'id="motionToggleButton"' in page
        and 'id="presentationModeButton"' in page,
        "visual_acceptance_console_present": 'id="visualAuditButton"' in page
        and 'id="visualAuditResults"' in page,
        "two_target_viewports_passed": len(audits) == 2
        and all(item.get("status") == "passed" for item in audits),
        "measurements_are_real_browser_dom": bool(audits)
        and all(
            item.get("measurement") == "same_origin_browser_dom"
            and item.get("user_agent_present") is True
            for item in audits
        ),
        "no_horizontal_or_component_overflow": bool(audits)
        and all(
            int(item.get("scroll_width") or 0) <= int(item.get("viewport_width") or 0)
            and not item.get("critical_overflows")
            for item in audits
        ),
        "all_required_behavior_checks_passed": bool(audits)
        and all(
            all((item.get("checks") or {}).get(key) is True for key in required_checks)
            for item in audits
        ),
        "state_keywords_at_least_16px": bool(audits)
        and all(float((item.get("checks") or {}).get("min_status_font_px") or 0) >= 16 for item in audits),
        "four_critical_components_and_titles_visible": bool(audits)
        and all(
            int((item.get("checks") or {}).get("critical_component_count") or 0) >= 4
            and int((item.get("checks") or {}).get("conclusion_title_count") or 0) >= 4
            for item in audits
        ),
        "main_case_is_real_opportunity": main_case.get("source_type") == "opportunity"
        and main_case.get("evidence_kind") == "public_record",
        "main_case_identity_matches_audits": bool(main_case.get("source_id"))
        and all(item.get("notice_id") == main_case.get("source_id") for item in audits),
        "semantic_state_contract_present": all(
            token in stylesheet
            for token in ("--tt-verified", "--tt-review", "--tt-gap", "--tt-system", "--tt-human")
        )
        and "semanticStateTag" in javascript,
        "motion_contract_present": "--tt-motion-productive: 320ms" in stylesheet
        and "--tt-motion-expressive: 480ms" in stylesheet
        and ".motion-disabled *" in stylesheet
        and "prefers-reduced-motion: reduce" in stylesheet,
        "target_breakpoints_present": "@media (min-width: 1600px)" in stylesheet
        and "@media (max-width: 1500px)" in stylesheet,
        "critical_local_environment_ready": environment.get("critical_ready") is True,
        "feishu_connection_ready": environment_checks.get("feishu", {}).get("status") == "ready",
        "source_health_reported_honestly": set(
            (environment.get("source_health_counts") or {}).keys()
        )
        == {"healthy", "degraded", "unhealthy", "unknown"},
    }
    payload = {
        "direction": 15,
        "name": "统一视觉、状态语言与业务动效",
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": BASE_URL,
        "direct_url": f"{BASE_URL}/?view=demoConsoleView",
        "main_case": {
            key: main_case.get(key)
            for key in (
                "label",
                "source_type",
                "source_id",
                "source_version",
                "data_as_of",
                "evidence_kind",
            )
        },
        "audits": audits,
        "state_language": visual.get("state_language") or [],
        "motion": visual.get("motion") or {},
        "environment": environment,
        "checks": checks,
        "passed": all(checks.values()),
        "notes": [
            "两种视口均由内置浏览器中的同源 iframe 加载真实主案例后测量，不使用手工填写结果。",
            "主案例验收同时打开数字孪生、证据显微镜、公告变更影响和飞书战情室。",
            "数据源降级或异常会继续保留在环境状态中，不因视觉验收而改写。",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
