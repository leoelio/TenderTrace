from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from tendertrace.app.api import create_app
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.digital_twin import build_digital_twin
from tendertrace.source_relation_graph import (
    build_source_relation_graph,
    decide_source_relation,
)


class SourceRelationGraphTests(unittest.TestCase):
    def test_graph_explains_cross_source_matches_and_keeps_conflicts_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)

            graph = build_source_relation_graph(settings, "official-original")

        assert graph is not None
        by_id = {item["related_notice_id"]: item for item in graph["relations"]}
        self.assertIn("repost-original", by_id)
        self.assertIn("official-correction", by_id)
        repost = by_id["repost-original"]
        self.assertEqual(repost["source_kind"], "repost")
        self.assertGreaterEqual(repost["score"], 90)
        self.assertIn("项目编号", [item["label"] for item in repost["deterministic_basis"]])
        correction = by_id["official-correction"]
        self.assertEqual(correction["notice_type"], "correction")
        self.assertIn("预算", [item["field_label"] for item in correction["conflicts"]])
        self.assertTrue(graph["rules"]["conflicts_never_auto_resolved"])
        blocked_ids = {item["related_notice_id"] for item in graph["blocked_candidates"]}
        self.assertIn("false-same-title", blocked_ids)

    def test_manual_split_is_locked_and_survives_incremental_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)

            decided = decide_source_relation(
                settings,
                "official-original",
                "repost-original",
                action="split",
                actor="reviewer",
                reason="来源页面实际对应不同采购包",
            )
            rebuilt = build_source_relation_graph(settings, "official-original")

        assert rebuilt is not None
        relation = next(item for item in rebuilt["relations"] if item["related_notice_id"] == "repost-original")
        self.assertEqual(relation["status"], "rejected")
        self.assertTrue(relation["decision"]["locked"])
        self.assertEqual(decided["decision_result"]["action"], "split")

    def test_merge_and_lock_flow_back_to_digital_twin_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            decide_source_relation(
                settings,
                "official-original",
                "repost-original",
                action="lock",
                actor="reviewer",
                reason="项目编号、采购人、预算与标题均一致，锁定同一项目",
            )

            twin = build_digital_twin(settings, "official-original")

        assert twin is not None
        self.assertEqual(twin["counts"]["confirmed_source_relations"], 1)
        self.assertTrue(any(item["type"] == "source_relation" for item in twin["timeline"]))
        self.assertEqual(twin["source_relations"]["summary"]["confirmed_count"], 1)

    def test_api_reads_graph_and_records_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {
                "TENDERTRACE_DB_PATH": os.environ.get("TENDERTRACE_DB_PATH"),
                "TENDERTRACE_SCHEDULER_ENABLED": os.environ.get("TENDERTRACE_SCHEDULER_ENABLED"),
            }
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "api.sqlite3")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                settings = Settings.load(root)
                init_db(settings)
                _seed(settings)
                client = TestClient(create_app())
                read = client.get("/api/opportunities/official-original/source-relations")
                decided = client.post(
                    "/api/opportunities/official-original/source-relations/repost-original/decision",
                    json={"action": "merge", "actor": "reviewer", "reason": "已回查两个来源原文"},
                )
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(read.status_code, 200)
        self.assertEqual(decided.status_code, 200)
        self.assertEqual(decided.json()["decision_result"]["decision"], "confirmed")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed(settings: Settings) -> None:
    rows = [
        (
            "official-original", "pbc_procurement", "https://official.example/original",
            "综合物业及保安与中控值机服务采购项目（包1）招标公告", "中国银行间市场交易商协会",
            "北京", "2026-09-11", "067GSF2026091", "44822800元", "tender", "采购公告",
            "采购人名称：中国银行间市场交易商协会；项目编号：067GSF2026091；预算金额：44822800元。",
        ),
        (
            "repost-original", "yfbzb", "https://repost.example/original",
            "中国银行间市场交易商协会综合物业及保安与中控值机服务采购项目（包1）招标公告",
            "中国银行间市场交易商协会", "北京市", "2026-09-11", "067GSF2026091", "44822800元",
            "repost", "转载公告", "采购人名称：中国银行间市场交易商协会；预算金额：44822800元。",
        ),
        (
            "official-correction", "pbc_procurement", "https://official.example/correction",
            "综合物业及保安与中控值机服务采购项目（包1）采购更正公告（第一次）", "中国银行间市场交易商协会",
            "北京", "2026-09-23", "067GSF2026091", "30000000元", "correction", "更正公告",
            "采购人名称：中国银行间市场交易商协会；项目编号：067GSF2026091；更正预算金额：30000000元。",
        ),
        (
            "false-same-title", "ggzy", "https://official.example/unrelated",
            "综合物业及保安与中控值机服务采购项目（包1）招标公告", "另一采购单位", "北京", "2026-09-11",
            "DIFFERENT-001", "100000元", "tender", "采购公告",
            "采购人名称：另一采购单位；项目编号：DIFFERENT-001；预算金额：100000元。",
        ),
    ]
    with connection(settings) as conn:
        for row in rows:
            fields = {"project_no": row[7], "budget": row[8], "structured_fields": {"project_no": row[7], "budget": row[8]}}
            conn.execute(
                """
                INSERT INTO notices(
                    id, source_site, source_url, canonical_url, title, purchaser, region,
                    publish_time, content_text, core_content, fields_json, notice_type,
                    notice_type_label, snapshot_sha256, updated_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'snapshot', datetime('now'), datetime('now'))
                """,
                (row[0], row[1], row[2], row[2], row[3], row[4], row[5], row[6], row[11], row[11], json.dumps(fields, ensure_ascii=False), row[9], row[10]),
            )


if __name__ == "__main__":
    unittest.main()
