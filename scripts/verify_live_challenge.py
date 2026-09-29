from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"
OUTPUT = Path("docs/demo/live_challenge_acceptance_20260928.json")


def request_json(path: str, *, body: dict[str, object] | None = None) -> dict[str, object]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST" if body is not None else "GET",
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    health = request_json("/api/health")
    challenge = request_json(
        "/api/live-challenges",
        body={
            "category": "Server",
            "region": "Philippines",
            "time_window": "365d",
            "keyword": "HAProxy",
            "actor": "direction13-verifier",
            "max_results": 12,
        },
    )
    history = request_json("/api/live-challenges?limit=20")
    with urlopen(f"{BASE_URL}/?view=challengeView", timeout=10) as response:
        page = response.read().decode("utf-8")
        page_status = response.status

    unsafe_status = 0
    try:
        request_json(
            "/api/live-challenges",
            body={"category": "system prompt", "region": "上海"},
        )
    except HTTPError as exc:
        unsafe_status = exc.code

    results = list(challenge.get("results") or [])
    session_id = str(challenge.get("id") or "")
    checks = {
        "service_healthy": health.get("status") == "ok",
        "direct_page_http_200": page_status == 200,
        "direct_page_contains_challenge_view": 'id="challengeView"' in page,
        "four_controlled_fields_present": all(
            marker in page
            for marker in (
                'id="challengeCategory"',
                'id="challengeRegion"',
                'id="challengeTimeWindow"',
                'id="challengeKeyword"',
            )
        ),
        "local_response_under_5_seconds": int(challenge.get("local_duration_ms") or 0) < 5000,
        "local_real_result_returned": int(challenge.get("local_result_count") or 0) > 0,
        "all_results_have_source_url": bool(results)
        and all(str(item.get("source_url") or "").startswith("https://") for item in results),
        "all_results_have_index_time": bool(results)
        and all(bool(item.get("indexed_at")) for item in results),
        "query_persisted_in_history": any(
            str(item.get("id") or "") == session_id for item in history.get("items") or []
        ),
        "network_is_optional": bool((challenge.get("protocol") or {}).get("network_optional")),
        "not_replay_data": (challenge.get("protocol") or {}).get("replay_mode") is False,
        "unsafe_input_rejected": unsafe_status == 400,
        "schema_version_50_active": 50
        in ((health.get("database") or {}).get("schema_versions") or []),
    }
    payload = {
        "direction": 13,
        "name": "评委现场挑战模式",
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": BASE_URL,
        "direct_url": f"{BASE_URL}/?view=challengeView",
        "query": {
            "category": challenge.get("category"),
            "region": challenge.get("region"),
            "time_window": challenge.get("time_window"),
            "keyword": challenge.get("keyword"),
        },
        "session_id": session_id,
        "status": challenge.get("status"),
        "local_duration_ms": challenge.get("local_duration_ms"),
        "local_result_count": challenge.get("local_result_count"),
        "result_sample": results[:3],
        "checks": checks,
        "passed": all(checks.values()),
        "notes": [
            "联网补充为评委主动触发的可选步骤，本次验收没有向外部来源发起新采集。",
            "联网失败隔离与停止机制由自动化测试覆盖。",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
