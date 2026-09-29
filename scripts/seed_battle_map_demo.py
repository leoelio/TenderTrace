from __future__ import annotations

import json
from pathlib import Path

from tendertrace.battle_map import (
    build_battle_map,
    evaluate_external_event_impacts,
    fetch_usgs_external_events,
    save_battle_map_replay,
    sync_business_events,
)
from tendertrace.config import Settings


ROOT = Path(__file__).resolve().parents[1]


def seed() -> dict[str, object]:
    settings = Settings.load(ROOT)
    business = sync_business_events(settings)
    external = fetch_usgs_external_events(settings, limit=60)
    evaluations = [
        evaluate_external_event_impacts(settings, event_id, actor="direction17-demo")
        for event_id in external["event_ids"]
    ]
    global_payload = build_battle_map(
        settings, scope="global", window_hours=2160, category="服务器"
    )
    china_payload = build_battle_map(
        settings, scope="china", window_hours=2160, category="服务器"
    )
    global_replay = save_battle_map_replay(
        settings,
        scope="global",
        window_hours=2160,
        category="服务器",
        actor="direction17-demo",
        verified=True,
    )
    china_replay = save_battle_map_replay(
        settings,
        scope="china",
        window_hours=2160,
        category="服务器",
        actor="direction17-demo",
        verified=True,
    )
    philippines = next(
        (
            card
            for card in global_payload["impact_cards"]
            if "Philippines" in card["event"]["region_name"] and card["impact_count"]
        ),
        None,
    )
    result = {
        "demo_url": "http://127.0.0.1:8000/?view=battleMapView&battle_scope=global&battle_hours=2160",
        "source_contract": {
            "name": "USGS Earthquake GeoJSON Feed",
            "url": external["source_url"],
            "license": "USGS public domain",
            "frequency": "official feed updated every minute; TenderTrace fetches only on explicit sync",
            "captured_count": external["imported_count"],
            "source_generated_at": external["source_generated_at"],
        },
        "business_sync": business,
        "global_summary": global_payload["summary"],
        "china_summary": china_payload["summary"],
        "evaluated_event_count": len(evaluations),
        "candidate_impact_count": sum(
            int(item["candidate_impact_count"]) for item in evaluations
        ),
        "featured_case": philippines,
        "replays": {
            "global": {
                key: global_replay[key]
                for key in ("id", "state_hash", "data_as_of", "verified_at")
            },
            "china": {
                key: china_replay[key]
                for key in ("id", "state_hash", "data_as_of", "verified_at")
            },
        },
        "interpretation_boundary": (
            "USGS 地震事实与 TenderTrace 业务影响分开保存；同国或距离规则只生成待人工复核候选，"
            "不会改写原机会、尽调或投标结论。"
        ),
    }
    output = ROOT / "docs" / "demo" / "battle_map_live_demo_20260929.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(seed(), ensure_ascii=False, indent=2))
