from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/demo/demo_reliability_acceptance_20260928.json"


def request_json(path: str, *, body: dict[str, object] | None = None) -> dict[str, object]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST" if body is not None else "GET",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    health = request_json("/api/health")
    request_json("/api/demo-reliability/prepare", body={"actor": "direction14-verifier"})
    initial = request_json("/api/demo-reliability")
    cases = {str(item["role"]): item for item in initial.get("cases") or []}

    plan = [
        ("main", "live", True, 1440, 900, "main-live"),
        ("backup", "verified_history", True, 1920, 1080, "backup-history"),
        ("replay", "live", False, 1440, 900, "offline-replay"),
    ]
    runs = []
    for role, mode, online, width, height, scenario in plan:
        result = request_json(
            "/api/demo-reliability/rehearsals",
            body={
                "case_id": cases[role]["id"],
                "requested_mode": mode,
                "browser_online": online,
                "viewport_width": width,
                "viewport_height": height,
                "scenario": scenario,
                "actor": "direction14-verifier",
            },
        )
        runs.append(result["rehearsal"])

    overview = request_json("/api/demo-reliability")
    cases = list(overview.get("cases") or [])
    layouts = list(overview.get("layout_audits") or [])
    environment = dict(overview.get("environment") or {})
    environment_checks = {
        str(item.get("key") or ""): item for item in environment.get("checks") or []
    }
    with urlopen(f"{BASE_URL}/?view=demoConsoleView", timeout=10) as response:
        page = response.read().decode("utf-8")
        page_status = response.status

    public_roles = {
        str(item.get("role") or "")
        for item in cases
        if item.get("evidence_kind") == "public_record"
    }
    replay_case = next((item for item in cases if item.get("role") == "replay"), {})
    checks = {
        "service_healthy": health.get("status") == "ok",
        "schema_version_51_active": 51
        in ((health.get("database") or {}).get("schema_versions") or []),
        "direct_page_http_200": page_status == 200,
        "console_is_present": 'id="demoConsoleView"' in page,
        "three_frozen_cases": len(cases) == 3
        and {str(item.get("role") or "") for item in cases} == {"main", "backup", "replay"},
        "all_snapshots_verified": bool(cases)
        and all(item.get("snapshot_verified") is True for item in cases),
        "all_same_version_replays_verified": bool(cases)
        and all(item.get("replay_verified") is True for item in cases),
        "main_and_backup_are_public_records": {"main", "backup"}.issubset(public_roles),
        "controlled_fixture_is_explicit": replay_case.get("evidence_kind")
        == "controlled_fixture"
        and "受控" in str(replay_case.get("label") or ""),
        "three_rehearsals_passed": len(runs) == 3
        and all(item.get("status") == "passed" for item in runs),
        "all_rehearsals_under_10_seconds": bool(runs)
        and all(int(item.get("opened_in_ms") or 0) < 10_000 for item in runs),
        "five_receipted_steps_per_run": bool(runs)
        and all(
            len(item.get("events") or []) == 5
            and all(event.get("receipt") for event in item.get("events") or [])
            for item in runs
        ),
        "offline_fails_over_to_same_version_replay": runs[-1].get("actual_mode") == "replay"
        and "离线" in str(runs[-1].get("switch_reason") or ""),
        "latest_three_are_consecutive_passes": bool(
            (overview.get("summary") or {}).get("consecutive_passes")
        ),
        "two_real_browser_layout_profiles_passed": len(layouts) == 2
        and all(
            item.get("status") == "passed"
            and item.get("measurement") == "same_origin_browser_dom"
            and item.get("user_agent_present") is True
            and not item.get("critical_overflows")
            for item in layouts
        ),
        "critical_local_environment_ready": environment.get("critical_ready") is True,
        "feishu_connection_ready": environment_checks.get("feishu", {}).get("status") == "ready",
        "source_health_is_reported_without_hiding_failures": set(
            (environment.get("source_health_counts") or {}).keys()
        ) == {"healthy", "degraded", "unhealthy", "unknown"},
    }
    payload = {
        "direction": 14,
        "name": "演示可靠性与真实回放控制台",
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": BASE_URL,
        "direct_url": f"{BASE_URL}/?view=demoConsoleView",
        "cases": [
            {
                key: item.get(key)
                for key in (
                    "role",
                    "label",
                    "source_type",
                    "source_id",
                    "source_version",
                    "data_as_of",
                    "evidence_kind",
                    "snapshot_verified",
                    "replay_verified",
                )
            }
            for item in cases
        ],
        "rehearsals": runs,
        "layout_audits": layouts,
        "environment": environment,
        "checks": checks,
        "passed": all(checks.values()),
        "notes": [
            "主案例与备案例取自本地数据库中已经采集的公开记录；回放案例若使用演练记录，会明确标识为受控夹具。",
            "回放只读取此前保存的请求、结果与回执，并校验同一数据版本和快照哈希。",
            "外部来源健康状态是动态实测值；降级和异常会保留显示，不会被验收脚本改写为健康。",
            "布局证据来自同源浏览器 iframe 的真实 DOM 尺寸与溢出测量，不是手工填写。",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
