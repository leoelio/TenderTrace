from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.digital_twin import _persist_snapshot, build_digital_twin
from tendertrace.opportunity_requirements import upsert_requirement


class DigitalTwinTests(unittest.TestCase):
    def test_builds_explainable_scores_and_only_snapshots_real_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            requirement = _save_requirement(settings, "QUAL-01", status="confirmed")
            _insert_confirmed_capability_match(settings, requirement.id)

            first = build_digital_twin(settings, "notice-digital-1")
            unchanged = build_digital_twin(settings, "notice-digital-1")
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE opportunity_requirements SET note = ? WHERE id = ?",
                    ("同一秒内修订但不改变数量或分数", requirement.id),
                )
            content_changed = build_digital_twin(settings, "notice-digital-1")
            with connection(settings) as conn:
                conn.execute(
                    "UPDATE opportunity_requirements SET note = NULL WHERE id = ?",
                    (requirement.id,),
                )
            reverted = build_digital_twin(settings, "notice-digital-1")
            _save_requirement(settings, "ATTACH-02", status="pending")
            changed = build_digital_twin(settings, "notice-digital-1")

            assert first is not None
            assert unchanged is not None
            assert content_changed is not None
            assert reverted is not None
            assert changed is not None
            self.assertEqual(
                set(first["scores"]),
                {"opportunity_value", "enterprise_fit", "bid_readiness"},
            )
            for score in first["scores"].values():
                self.assertTrue(score["components"])
                self.assertTrue(all(component["evidence"] for component in score["components"]))
                self.assertTrue(all(component["source_path"] for component in score["components"]))
            self.assertEqual(first["snapshot"]["status"], "changed")
            self.assertEqual(unchanged["snapshot"]["status"], "unchanged")
            self.assertEqual(len(unchanged["snapshot"]["history"]), 1)
            self.assertEqual(content_changed["snapshot"]["status"], "changed")
            self.assertEqual(len(content_changed["snapshot"]["history"]), 2)
            self.assertEqual(
                content_changed["snapshot"]["changes_since_previous"][0]["label"],
                "档案内容",
            )
            self.assertEqual(reverted["snapshot"]["status"], "changed")
            self.assertEqual(len(reverted["snapshot"]["history"]), 3)
            self.assertEqual(reverted["snapshot"]["state_hash"], first["snapshot"]["state_hash"])
            self.assertEqual(changed["snapshot"]["status"], "changed")
            self.assertEqual(len(changed["snapshot"]["history"]), 4)
            self.assertTrue(
                any(item["label"] == "要求账本" for item in changed["snapshot"]["changes_since_previous"])
            )

    def test_missing_capability_matches_do_not_earn_gap_or_technical_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            _save_requirement(settings, "QUAL-01", status="confirmed")

            result = build_digital_twin(settings, "notice-digital-1")

            assert result is not None
            fit = result["scores"]["enterprise_fit"]
            readiness = result["scores"]["bid_readiness"]
            gap_control = next(item for item in fit["components"] if item["key"] == "gap_control")
            technical = next(item for item in readiness["components"] if item["key"] == "technical")
            self.assertEqual(fit["status"], "insufficient")
            self.assertEqual(gap_control["score"], 0)
            self.assertEqual(technical["score"], 0)

    def test_concurrent_refresh_records_one_history_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            summary = {"scores": {}, "counts": {}, "source_freshness": {}}
            _persist_snapshot(settings, "notice-digital-1", "state-a", summary)

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda _: _persist_snapshot(
                            settings,
                            "notice-digital-1",
                            "state-b",
                            summary,
                        ),
                        range(2),
                    )
                )

            self.assertEqual(
                sorted(item["status"] for item in results),
                ["changed", "unchanged"],
            )
            with connection(settings) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) AS total FROM opportunity_digital_twin_history WHERE notice_id = ?",
                    ("notice-digital-1",),
                ).fetchone()["total"]
            self.assertEqual(count, 2)

    def test_api_exposes_current_dossier_without_external_calls(self) -> None:
        from fastapi.testclient import TestClient

        from tendertrace.app.api import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = {
                "TENDERTRACE_DB_PATH": os.environ.get("TENDERTRACE_DB_PATH"),
                "TENDERTRACE_SCHEDULER_ENABLED": os.environ.get("TENDERTRACE_SCHEDULER_ENABLED"),
            }
            os.environ["TENDERTRACE_DB_PATH"] = str(root / "data" / "api.sqlite3")
            os.environ["TENDERTRACE_SCHEDULER_ENABLED"] = "false"
            try:
                settings = Settings.load()
                init_db(settings)
                _insert_notice(settings)
                client = TestClient(create_app())
                response = client.get("/api/opportunities/notice-digital-1/digital-twin")
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["notice_id"], "notice-digital-1")
        self.assertEqual(body["refresh"]["mode"], "on_read_plus_30s_polling")
        self.assertEqual(body["scores"]["enterprise_fit"]["status"], "insufficient")

    def test_war_room_resources_are_counted_in_collaboration_dossier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            with connection(settings) as conn:
                conn.execute(
                    "INSERT INTO feishu_war_rooms(id, notice_id, status) VALUES ('room-1', 'notice-digital-1', 'started')"
                )
                conn.execute(
                    """
                    INSERT INTO feishu_war_room_steps(
                        id, war_room_id, notice_id, step_key, label, status,
                        idempotency_key, resource_type, resource_id
                    ) VALUES ('step-1', 'room-1', 'notice-digital-1', 'group_card',
                        '项目总览卡片', 'completed', 'idem-1', 'message', 'om-demo')
                    """
                )

            result = build_digital_twin(settings, "notice-digital-1")

        assert result is not None
        self.assertEqual(result["counts"]["war_room_resources"], 1)
        collaboration = next(item for item in result["dossier_sections"] if item["key"] == "collaboration")
        self.assertEqual(collaboration["count"], 1)

    def test_enterprise_bid_memory_is_counted_in_project_dossier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            with connection(settings) as conn:
                conn.execute("INSERT INTO organization_workspaces(id, name, feishu_chat_id, created_by) VALUES ('ws-memory', '企业经验', 'oc-memory', 'admin')")
                conn.execute("INSERT INTO bid_memory_projects(id, workspace_id, notice_id, outcome_result, summary, lessons, created_by) VALUES ('project-memory', 'ws-memory', 'notice-digital-1', 'won', '结果已核验', '经验已复盘', 'admin')")
                conn.execute("INSERT INTO bid_memory_assets(id, project_memory_id, workspace_id, source_notice_id, asset_key, asset_type, title, content, reuse_status) VALUES ('asset-memory', 'project-memory', 'ws-memory', 'notice-digital-1', 'lesson', 'lesson', '历史经验', '可追溯经验', 'reusable')")

            result = build_digital_twin(settings, "notice-digital-1")

        assert result is not None
        self.assertEqual(result["counts"]["bid_memory_projects"], 1)
        self.assertEqual(result["counts"]["bid_memory_assets"], 1)
        memory = next(item for item in result["dossier_sections"] if item["key"] == "memory")
        self.assertEqual(memory["count"], 2)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n"
        "TENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    today = date.today()
    deadline = today + timedelta(days=30)
    fields = {
        "structured_fields": {
            "project_no": "TT-DIGITAL-001",
            "budget": "500万元",
            "bid_deadline": deadline.isoformat(),
        }
    }
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json,
                updated_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "notice-digital-1",
                "ccgp",
                "https://example.com/notices/digital-1",
                "https://example.com/notices/digital-1",
                "数字化平台采购项目",
                "示例采购中心",
                today.isoformat(),
                "北京",
                "数字化平台采购项目，预算500万元，包含资格、技术与交付要求。",
                "建设数字化业务平台并完成实施交付。",
                json.dumps(fields, ensure_ascii=False),
            ),
        )


def _save_requirement(settings: Settings, key: str, *, status: str):
    return upsert_requirement(
        settings,
        notice_id="notice-digital-1",
        requirement_key=key,
        requirement_type="qualification" if key.startswith("QUAL") else "attachment",
        title="信息安全认证" if key.startswith("QUAL") else "项目实施方案",
        evidence_text="投标人须提供有效证书及可核验材料。",
        source_url="https://example.com/notices/digital-1",
        source_locator="采购文件第 3 页",
        mandatory=True,
        confidence=95,
        status=status,
        actor="test",
    )


def _insert_confirmed_capability_match(settings: Settings, requirement_id: str) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO enterprise_capabilities(
                id, capability_key, title, capability_type, evidence_text,
                source_url, source_locator, verification_status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'verified', 'test')
            """,
            (
                "capability-1",
                "security-cert",
                "信息安全认证能力",
                "qualification",
                "证书在有效期内。",
                "https://example.com/capabilities/security-cert",
                "证书第 1 页",
            ),
        )
        conn.execute(
            """
            INSERT INTO requirement_capability_matches(
                id, notice_id, requirement_id, capability_id, verdict,
                confidence, rationale, status, decided_by, decision_note, decided_at
            ) VALUES (?, ?, ?, ?, 'supported', 96, ?, 'confirmed', 'reviewer', ?, datetime('now'))
            """,
            (
                "match-1",
                "notice-digital-1",
                requirement_id,
                "capability-1",
                "企业证书与资格要求一致。",
                "已核验证书编号和有效期。",
            ),
        )
