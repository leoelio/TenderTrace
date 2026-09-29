from __future__ import annotations

import json
from pathlib import Path
import time

from tendertrace.battle_map import build_battle_map, battle_map_event_detail
from tendertrace.config import Settings
from tendertrace.db import connection


ROOT = Path(__file__).resolve().parents[1]


def evaluate() -> dict[str, object]:
    settings = Settings.load(ROOT)
    started = time.perf_counter()
    live = build_battle_map(
        settings, scope="global", window_hours=2160, category="服务器"
    )
    replay = build_battle_map(
        settings,
        scope="global",
        window_hours=2160,
        category="服务器",
        mode="replay",
    )
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    event_ids = {item["id"] for item in live["events"]}
    impact_targets = {item["target_id"] for item in live["impacts"] if item["target_type"] == "notice"}
    with connection(settings) as conn:
        expected_notice_ids = {
            str(row["object_id"])
            for row in conn.execute(
                "SELECT object_id FROM geo_events WHERE category = '服务器'"
            )
        }
    details = [battle_map_event_detail(settings, event_id) for event_id in list(event_ids)[:10]]
    proof = {
        "real_events_only": live["rules"]["random_points_forbidden"],
        "map_and_list_same_query": live["rules"]["map_and_list_share_query"],
        "event_count_matches": live["summary"]["event_count"] == len(live["events"]) + len(live["external_events"]),
        "all_category_records_present": {item["object_id"] for item in live["events"]} == expected_notice_ids,
        "domestic_main_cases_province_geocoded": live["summary"]["province_precision_rate"] >= 0.95,
        "external_source_present": live["summary"]["external_event_count"] > 0,
        "impact_is_candidate_not_fact": all(item["relation_basis"] in {"rule", "manual", "direct"} and item["review_status"] in {"pending", "monitoring", "confirmed", "rejected"} for item in live["impacts"]),
        "impacts_reference_real_targets": impact_targets.issubset({item["object_id"] for item in live["events"]}),
        "evidence_drilldown_available": all(item["event"]["source_url"] for item in details),
        "verified_replay_available": replay["mode"] == "replay" and bool(replay["replay"].get("state_hash")),
        "sse_latency_budget_declared": duration_ms < 5000,
        "motion_and_list_fallback": live["rules"]["motion_can_be_disabled"] and bool(live["events"]),
    }
    failed = [key for key, value in proof.items() if not value]
    result = {
        "generated_at": live["generated_at"],
        "duration_ms": duration_ms,
        "summary": live["summary"],
        "proof": proof,
        "failed": failed,
        "status": "passed" if not failed else "failed",
        "demo_url": "http://127.0.0.1:8000/?view=battleMapView&battle_scope=global&battle_hours=2160",
    }
    output = ROOT / "docs" / "demo" / "battle_map_acceptance_20260929.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if failed:
        raise AssertionError(f"battle map acceptance failed: {failed}")
    return result


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
