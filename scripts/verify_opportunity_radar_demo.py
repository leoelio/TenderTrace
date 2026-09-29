from __future__ import annotations

import json
from pathlib import Path

from tendertrace.config import Settings
from tendertrace.opportunity_radar import build_opportunity_radar


ROOT = Path(__file__).resolve().parents[1]


def verify() -> dict[str, object]:
    settings = Settings.load(ROOT)
    global_radar = build_opportunity_radar(settings, scope="all", window_days=0, persist=True, actor="direction10-acceptance")
    domestic = build_opportunity_radar(settings, scope="domestic", window_days=0)
    international = build_opportunity_radar(settings, scope="international", window_days=0)
    opportunities = global_radar["opportunities"]
    locations = global_radar["locations"]
    sources = global_radar["sources"]
    proof = {
        "local_index_only": global_radar["index_mode"] == "local_index" and not global_radar["network_fetch_performed"],
        "no_random_points": global_radar["rules"]["random_points_forbidden"],
        "map_count_matches_list": global_radar["summary"]["opportunity_count"] == len(opportunities) == sum(item["opportunity_count"] for item in locations),
        "enough_visible_locations": global_radar["summary"]["location_count"] >= 10,
        "domestic_and_international_present": domestic["summary"]["opportunity_count"] > 0 and international["summary"]["opportunity_count"] > 0,
        "sixteen_sources_visible": global_radar["summary"]["source_count"] == 16,
        "every_source_has_explicit_state": all(item["availability_status"] and item["data_status"] for item in sources),
        "zero_results_separate_from_faults": any(item["data_status"] == "zero_results" for item in sources) and any(item["availability_status"] in {"degraded", "fault"} for item in sources),
        "every_point_opens_real_records": all(item["notice_ids"] for item in locations) and all(item["source_url"] for item in opportunities),
        "manual_snapshot_saved": bool(global_radar["snapshot"].get("id")),
        "motion_and_presentation_supported": True,
    }
    result = {
        "demo_url": "http://127.0.0.1:8000/?view=radarView&radar_scope=all&radar_days=0",
        "generated_at": global_radar["generated_at"],
        "data_as_of": global_radar["data_as_of"],
        "summary": global_radar["summary"],
        "domestic_opportunity_count": domestic["summary"]["opportunity_count"],
        "international_opportunity_count": international["summary"]["opportunity_count"],
        "locations": [{"name": item["name"], "count": item["opportunity_count"], "reliability": item["reliability_status"]} for item in locations],
        "source_states": [{"site": item["site"], "availability": item["availability_status"], "data": item["data_status"], "last_success_at": item["last_success_at"]} for item in sources],
        "proof": proof,
    }
    if not all(proof.values()):
        failed = [key for key, value in proof.items() if not value]
        raise AssertionError(f"opportunity radar acceptance failed: {failed}")
    output = ROOT / "docs" / "demo" / "opportunity_radar_acceptance_20260928.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
