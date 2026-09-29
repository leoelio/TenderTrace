from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.app import api as api_module
from tendertrace.battle_map import (
    battle_map_event_detail,
    build_battle_map,
    evaluate_external_event_impacts,
    fetch_usgs_external_events,
    review_impact_link,
    save_battle_map_replay,
    sync_business_events,
)
from tendertrace.config import Settings
from tendertrace.db import SCHEMA_VERSION, connection, database_health, init_db


class BattleMapTests(unittest.TestCase):
    def test_schema_and_business_event_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            result = sync_business_events(settings)
            payload = build_battle_map(settings, scope="global", window_hours=0)

        self.assertEqual(result, {"geo_events": 3, "awards": 1, "flows": 1})
        self.assertEqual(payload["summary"]["event_count"], 3)
        self.assertEqual(payload["summary"]["opportunity_count"], 2)
        self.assertEqual(payload["summary"]["award_count"], 1)
        self.assertEqual(payload["summary"]["flow_count"], 1)
        self.assertEqual(
            payload["summary"]["event_count"],
            len(payload["events"]) + len(payload["external_events"]),
        )
        self.assertTrue(payload["rules"]["random_points_forbidden"])
        self.assertTrue(payload["rules"]["map_and_list_share_query"])
        self.assertTrue(all(item["source_url"] for item in payload["events"]))
        award = next(item for item in payload["events"] if item["layer"] == "award")
        self.assertEqual(award["coordinate_precision"], "province")
        self.assertEqual(award["amount"], 88000)

    def test_official_external_event_only_creates_explainable_candidate_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            sync_business_events(settings)
            with patch("tendertrace.battle_map.httpx.get", return_value=_FakeResponse()):
                imported = fetch_usgs_external_events(settings, limit=10)
            evaluated = evaluate_external_event_impacts(
                settings, imported["event_ids"][0], actor="tester"
            )
            payload = build_battle_map(settings, scope="global", window_hours=0)

        self.assertEqual(imported["source"], "USGS")
        self.assertEqual(imported["imported_count"], 1)
        self.assertEqual(evaluated["candidate_impact_count"], 1)
        self.assertEqual(payload["summary"]["external_event_count"], 1)
        self.assertEqual(payload["summary"]["candidate_impact_count"], 1)
        impact = payload["impacts"][0]
        self.assertEqual(impact["relation_basis"], "rule")
        self.assertEqual(impact["review_status"], "pending")
        self.assertEqual(impact["rule_key"], "same-country-v1")
        self.assertIn("仍需核验", impact["explanation"])
        self.assertEqual(impact["match_basis"]["event_country"], "PH")

    def test_review_replay_and_evidence_drilldown_are_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            sync_business_events(settings)
            with patch("tendertrace.battle_map.httpx.get", return_value=_FakeResponse()):
                external = fetch_usgs_external_events(settings)
            evaluate_external_event_impacts(settings, external["event_ids"][0])
            live = build_battle_map(settings, scope="global", window_hours=0)
            reviewed = review_impact_link(
                settings,
                live["impacts"][0]["id"],
                status="monitoring",
                actor="reviewer",
                note="先核验实际交付地点与物流路线",
            )
            frame = save_battle_map_replay(
                settings,
                scope="global",
                window_hours=0,
                actor="tester",
                verified=True,
            )
            replay = build_battle_map(
                settings, scope="global", window_hours=0, mode="replay"
            )
            detail = battle_map_event_detail(settings, external["event_ids"][0])

        self.assertEqual(reviewed["review_status"], "monitoring")
        self.assertEqual(reviewed["reviewed_by"], "reviewer")
        self.assertTrue(frame["verified"])
        self.assertEqual(replay["mode"], "replay")
        self.assertEqual(replay["replay"]["state_hash"], frame["state_hash"])
        self.assertEqual(detail["kind"], "external_event")
        self.assertEqual(detail["event"]["source_license"], "USGS public domain")
        self.assertTrue(detail["event"]["snapshot_sha256"])

    def test_api_exposes_map_sync_review_and_replay(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            with patch.object(api_module.Settings, "load", return_value=settings):
                with TestClient(api_module.create_app()) as client:
                    synced = client.post("/api/battle-map/sync", json={})
                    loaded = client.get(
                        "/api/battle-map",
                        params={"scope": "global", "window_hours": 0},
                    )
                    replay = client.post(
                        "/api/battle-map/replays",
                        json={"scope": "global", "window_hours": 0, "verified": True},
                    )
                    detail_id = loaded.json()["events"][0]["id"]
                    detail = client.get(f"/api/battle-map/events/{detail_id}")

        self.assertEqual(synced.status_code, 200)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["summary"]["event_count"], 3)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["verified"])
        self.assertEqual(detail.status_code, 200)

    def test_database_health_lists_direction_seventeen_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            health = database_health(settings)
        self.assertEqual(health["schema_versions"][-1], SCHEMA_VERSION)
        self.assertTrue(
            {
                "geo_events",
                "business_flows",
                "external_events",
                "impact_links",
                "map_replay_frames",
            }.issubset(set(health["tables"]))
        )


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed_notices(settings: Settings) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = (
        (
            "battle-cn-opportunity",
            "ccgp",
            "北京",
            "北京市服务器扩容招标",
            "服务器",
            "公开招标公告",
        ),
        (
            "battle-ph-opportunity",
            "adb",
            "Philippines",
            "Philippines server modernization procurement",
            "服务器",
            "Procurement opportunity",
        ),
        (
            "battle-cn-award",
            "ggzy",
            "四川省",
            "机架式服务器直接选定采购合同",
            "服务器",
            "采购人名称 成都某研究院 中标（成交）供应商名称 成都华东电脑系统集成有限公司 合同金额 88,000元",
        ),
    )
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO company_entities(
                id, workspace_id, legal_name, region, created_by
            ) VALUES ('company-demo', 'workspace-demo', ?, '成都', 'tester')
            """,
            ("成都华东电脑系统集成有限公司",),
        )
        for notice_id, source, region, title, category, content in rows:
            fields = json.dumps(
                {
                    "structured_fields": {"category": category},
                    "evidence_status": "passed",
                },
                ensure_ascii=False,
            )
            conn.execute(
                """
                INSERT INTO notices(
                    id, source_site, source_url, canonical_url, title,
                    publish_time, region, purchaser, content_text,
                    core_content, fields_json, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '测试采购人', ?, ?, ?, ?)
                """,
                (
                    notice_id,
                    source,
                    f"https://example.com/{notice_id}",
                    f"https://example.com/{notice_id}",
                    title,
                    now,
                    region,
                    content,
                    content,
                    fields,
                    now,
                ),
            )


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        return {
            "metadata": {"generated": timestamp, "count": 1},
            "features": [
                {
                    "id": "us-test-ph",
                    "type": "Feature",
                    "properties": {
                        "mag": 5.2,
                        "place": "124 km SE of Pondaguitan, Philippines",
                        "time": timestamp,
                        "updated": timestamp,
                        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us-test-ph",
                        "detail": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/us-test-ph.geojson",
                        "status": "reviewed",
                        "type": "earthquake",
                    },
                    "geometry": {"type": "Point", "coordinates": [126.3, 5.2, 50]},
                }
            ],
        }


if __name__ == "__main__":
    unittest.main()
