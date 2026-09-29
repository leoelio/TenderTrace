from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.app import api as api_module
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_radar import build_opportunity_radar


class OpportunityRadarTests(unittest.TestCase):
    def test_global_radar_uses_local_index_and_separates_zero_results_from_faults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_radar(settings)

            radar = build_opportunity_radar(settings, scope="all", window_days=90)
            domestic = build_opportunity_radar(settings, scope="domestic", window_days=90)
            international = build_opportunity_radar(settings, scope="international", window_days=90)

        self.assertEqual(radar["summary"]["opportunity_count"], 7)
        self.assertEqual(domestic["summary"]["opportunity_count"], 2)
        self.assertEqual(international["summary"]["opportunity_count"], 5)
        self.assertGreaterEqual(radar["summary"]["location_count"], 6)
        self.assertEqual(radar["summary"]["source_count"], 16)
        self.assertFalse(radar["network_fetch_performed"])
        self.assertTrue(radar["rules"]["random_points_forbidden"])
        self.assertTrue(radar["rules"]["zero_results_separate_from_faults"])
        worldbank = next(item for item in radar["sources"] if item["site"] == "worldbank")
        canada = next(item for item in radar["sources"] if item["site"] == "canadabuys")
        qianlima = next(item for item in radar["sources"] if item["site"] == "qianlima")
        self.assertEqual(worldbank["availability_status"], "fault")
        self.assertEqual(worldbank["data_status"], "has_results")
        self.assertEqual(canada["availability_status"], "healthy")
        self.assertEqual(canada["data_status"], "zero_results")
        self.assertEqual(qianlima["availability_status"], "access_limited")
        self.assertTrue(all(item["notice_ids"] for item in radar["locations"]))
        self.assertTrue(all(item["source_url"] for item in radar["opportunities"]))

    def test_manual_refresh_persists_offline_snapshot_and_category_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_radar(settings)

            refreshed = build_opportunity_radar(settings, scope="all", window_days=90, category="服务器", persist=True, actor="tester")
            replay = build_opportunity_radar(settings, scope="all", window_days=90, category="服务器")

        self.assertEqual(refreshed["summary"]["opportunity_count"], 4)
        self.assertTrue(refreshed["snapshot"]["id"])
        self.assertEqual(refreshed["snapshot"]["created_by"], "tester")
        self.assertEqual(replay["snapshot"]["id"], refreshed["snapshot"]["id"])
        self.assertEqual({item["category"] for item in refreshed["opportunities"]}, {"服务器"})

    def test_api_exposes_read_and_manual_refresh(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_radar(settings)
            with patch.object(api_module.Settings, "load", return_value=settings):
                with TestClient(api_module.create_app()) as client:
                    loaded = client.get("/api/opportunity-radar", params={"scope": "all", "window_days": 90})
                    refreshed = client.post("/api/opportunity-radar/refresh", json={"scope": "international", "window_days": 90, "actor": "tester"})
                    invalid = client.get("/api/opportunity-radar", params={"scope": "moon"})

        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["summary"]["opportunity_count"], 7)
        self.assertEqual(refreshed.status_code, 200)
        self.assertTrue(refreshed.json()["snapshot"]["id"])
        self.assertEqual(invalid.status_code, 400)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text("TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n", encoding="utf-8")
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed_radar(settings: Settings) -> None:
    today = date.today()
    rows = (
        ("radar-cn-bj", "ccgp", "北京", "北京服务器扩容采购", "服务器"),
        ("radar-cn-zj", "ggzy", "浙江省", "浙江充电设施采购", "充电桩"),
        ("radar-eu-de", "ted", "DEU", "European data center servers", "服务器"),
        ("radar-af-mz", "afdb", "Mozambique", "Cloud server procurement", "服务器"),
        ("radar-la-uy", "idb", "Uruguay", "Medical equipment program", "医疗设备"),
        ("radar-as-ph", "adb", "Philippines", "Network server equipment", "服务器"),
        ("radar-wb-id", "worldbank", "Indonesia", "Cooling system procurement", "空调"),
    )
    with connection(settings) as conn:
        for index, (notice_id, source, region, title, category) in enumerate(rows):
            publish = (today - timedelta(days=index + 1)).isoformat()
            fields = json.dumps({"structured_fields": {"category": category}}, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO notices(id, source_site, source_url, canonical_url, title, publish_time, region, content_text, core_content, fields_json, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (notice_id, source, f"https://example.com/{notice_id}", f"https://example.com/{notice_id}", title, publish, region, title, title, fields),
            )
        observations = (
            ("ccgp", "completed", 1, "", {"requests": 2, "succeeded": 2, "avg_elapsed_ms": 500}),
            ("ggzy", "completed", 1, "", {"requests": 2, "succeeded": 2, "avg_elapsed_ms": 600}),
            ("ted", "completed", 1, "", {"requests": 1, "succeeded": 1, "avg_elapsed_ms": 700}),
            ("afdb", "completed", 1, "", {"requests": 1, "succeeded": 1, "avg_elapsed_ms": 1200}),
            ("idb", "completed", 1, "", {"requests": 1, "succeeded": 1, "avg_elapsed_ms": 900}),
            ("adb", "completed", 1, "", {"requests": 1, "succeeded": 1, "avg_elapsed_ms": 900}),
            ("canadabuys", "completed", 0, "", {"requests": 1, "succeeded": 1, "avg_elapsed_ms": 800}),
            ("worldbank", "failed", 1, "upstream timeout", {"requests": 1, "failed": 1, "avg_elapsed_ms": 5000}),
        )
        for site, status, count, error, stats in observations:
            conn.execute(
                "INSERT INTO source_observations(source_site, status, notice_count, error, fetch_stats_json) VALUES (?, ?, ?, NULLIF(?, ''), ?)",
                (site, status, count, error, json.dumps(stats)),
            )


if __name__ == "__main__":
    unittest.main()
