from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.app import api as api_module
from tendertrace.bid_memory import archive_project_memory, decide_bid_memory_asset, get_bid_memory_dashboard
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.opportunity_outcomes import record_outcome
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.organization_memory import create_workspace


class BidMemoryTests(unittest.TestCase):
    def test_similarity_graph_sample_boundary_expiry_and_workspace_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            workspace = create_workspace(
                settings,
                name="政务云投标中心",
                feishu_chat_id="oc_memory_team",
                members=[
                    {"open_id": "ou_owner", "name": "负责人", "role": "owner"},
                    {"open_id": "ou_observer", "name": "观察员", "role": "observer"},
                ],
                actor="ou_owner",
            )
            other = create_workspace(
                settings,
                name="其他事业部",
                feishu_chat_id="oc_memory_other",
                members=[{"open_id": "ou_other", "role": "owner"}],
                actor="ou_other",
            )
            _outcome(settings, "history-won", "won", "技术响应完整，复用安全方案模板。")
            _outcome(settings, "history-lost", "lost", "原厂授权过期导致资格风险。")
            _outcome(settings, "other-secret", "won", "其他组织的敏感经验。")
            for notice_id in ("history-won", "history-lost", "target-new"):
                upsert_requirement(
                    settings,
                    notice_id=notice_id,
                    requirement_key=f"TECH-{notice_id}",
                    requirement_type="technical",
                    title="政务云双活容灾与安全响应",
                    evidence_text="须提供双活容灾、安全响应和实施交付方案。",
                    source_url=f"https://example.com/{notice_id}",
                    source_locator="技术规格第20页",
                    mandatory=True,
                    status="confirmed",
                )
            archive_project_memory(
                settings,
                "history-won",
                workspace_id=workspace.id,
                actor="ou_owner",
                tags=["政务云", "北京", "安全"],
                materials=[{
                    "asset_key": "security-plan",
                    "title": "政务云安全响应模板",
                    "content": "已脱敏的安全响应章节，可按新项目参数更新。",
                    "valid_until": "2028-12-31",
                    "reuse_status": "reusable",
                    "permission_scope": "restricted",
                    "sensitivity": "sensitive",
                }],
            )
            archive_project_memory(
                settings,
                "history-lost",
                workspace_id=workspace.id,
                actor="ou_owner",
                tags=["政务云", "北京", "授权"],
                materials=[{
                    "asset_key": "expired-auth",
                    "asset_type": "material",
                    "title": "历史原厂授权函",
                    "content": "该授权函已经过期，不可直接用于新项目。",
                    "valid_until": "2025-12-31",
                    "reuse_status": "reusable",
                }, {
                    "asset_key": "authorization-gap",
                    "asset_type": "gap",
                    "title": "原厂专项授权缺口",
                    "content": "必须在投标前取得本项目和地区范围授权。",
                    "reuse_status": "reference",
                }],
            )
            archive_project_memory(settings, "other-secret", workspace_id=other.id, actor="ou_other")

            dashboard = get_bid_memory_dashboard(settings, workspace_id=workspace.id, notice_id="target-new", actor="ou_owner")
            observer = get_bid_memory_dashboard(settings, workspace_id=workspace.id, notice_id="target-new", actor="ou_observer")
            denied = get_bid_memory_dashboard(settings, workspace_id=other.id, notice_id="target-new", actor="ou_owner")

        self.assertTrue(dashboard["access"]["granted"])
        self.assertEqual(len(dashboard["recommendations"]), 2)
        self.assertTrue(dashboard["sample"]["reliable"])
        self.assertFalse(dashboard["sample"]["probability_output"])
        self.assertNotIn("win_probability", dashboard)
        self.assertEqual({item["result"] for item in dashboard["recommendations"]}, {"won", "lost"})
        self.assertTrue(all(item["reasons"] for item in dashboard["recommendations"]))
        self.assertTrue(all(item["source_notice_id"] for item in dashboard["recommendations"]))
        expired = next(item for item in dashboard["assets"] if item["asset_key"] == "expired-auth")
        self.assertEqual(expired["effective_status"], "expired")
        self.assertTrue({"target", "project", "customer", "region", "category", "task", "material", "gap", "outcome"}.issubset({item["type"] for item in dashboard["graph"]["nodes"]}))
        self.assertGreater(observer["summary"]["hidden_sensitive_count"], dashboard["summary"]["hidden_sensitive_count"])
        self.assertFalse(any(item["asset_key"] == "security-plan" for item in observer["assets"]))
        self.assertFalse(denied["access"]["granted"])
        self.assertFalse(any(item["notice_id"] == "other-secret" for item in dashboard["projects"]))

    def test_human_confirm_correct_withdraw_is_versioned_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            workspace = create_workspace(settings, name="投标记忆", feishu_chat_id="oc_memory_audit", members=[{"open_id": "ou_owner", "role": "owner"}], actor="ou_owner")
            _outcome(settings, "history-won", "won", "可复用项目经验。")
            archived = archive_project_memory(
                settings,
                "history-won",
                workspace_id=workspace.id,
                actor="ou_owner",
                materials=[{"asset_key": "manual", "title": "响应模板", "content": "第一版", "reuse_status": "update_needed"}],
            )
            asset = next(item for item in archived["assets"] if item["asset_key"] == "manual")
            confirmed = decide_bid_memory_asset(settings, asset["id"], workspace_id=workspace.id, action="confirm", actor="ou_owner", note="已核对适用范围")
            corrected = decide_bid_memory_asset(settings, asset["id"], workspace_id=workspace.id, action="correct", actor="ou_owner", note="补充新版章节", corrections={"content": "第二版，已完成脱敏", "reuse_status": "reusable", "valid_until": "2028-06-30"})
            withdrawn = decide_bid_memory_asset(settings, asset["id"], workspace_id=workspace.id, action="withdraw", actor="ou_owner", note="材料被新版本替代")
            dashboard = get_bid_memory_dashboard(settings, workspace_id=workspace.id, actor="ou_owner")

        self.assertEqual(confirmed["effective_status"], "reusable")
        self.assertEqual(corrected["version_number"], 2)
        self.assertEqual(corrected["content"], "第二版，已完成脱敏")
        self.assertEqual(withdrawn["effective_status"], "invalid")
        actions = [item["action"] for item in dashboard["audit"]]
        self.assertIn("asset_confirm", actions)
        self.assertIn("asset_correct", actions)
        self.assertIn("asset_withdraw", actions)

    def test_api_exposes_archive_dashboard_and_decision_routes(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed_notices(settings)
            workspace = create_workspace(settings, name="投标记忆", feishu_chat_id="oc_memory_api", members=[{"open_id": "ou_owner", "role": "owner"}], actor="ou_owner")
            _outcome(settings, "history-won", "won", "可复用项目经验。")
            with patch.object(api_module.Settings, "load", return_value=settings):
                with TestClient(api_module.create_app()) as client:
                    archived = client.post("/api/opportunities/history-won/bid-memory/archive", json={"workspace_id": workspace.id, "actor": "ou_owner", "tags": ["政务云"]})
                    dashboard = client.get(f"/api/organization/workspaces/{workspace.id}/bid-memory", params={"actor": "ou_owner"})
                    asset = next(item for item in dashboard.json()["assets"] if item["asset_type"] == "lesson")
                    decision = client.post(f"/api/organization/workspaces/{workspace.id}/bid-memory/assets/{asset['id']}/decision", json={"action": "confirm", "actor": "ou_owner", "note": "人工确认"})

        self.assertEqual(archived.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["asset"]["effective_status"], "reusable")


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text("TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n", encoding="utf-8")
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed_notices(settings: Settings) -> None:
    rows = (
        ("history-won", "北京政务云安全能力扩容项目", "某政务单位", "北京"),
        ("history-lost", "北京政务云容灾建设项目", "另一政务单位", "北京"),
        ("target-new", "北京政务云安全与双活容灾采购项目", "某政务单位", "北京"),
        ("other-secret", "其他组织服务器采购", "某企业", "上海"),
    )
    with connection(settings) as conn:
        for notice_id, title, purchaser, region in rows:
            conn.execute(
                "INSERT INTO notices(id, source_site, source_url, canonical_url, title, purchaser, region, core_content, content_text, fields_json) VALUES (?, 'demo', ?, ?, ?, ?, ?, ?, ?, ?)",
                (notice_id, f"https://example.com/{notice_id}", f"https://example.com/{notice_id}", title, purchaser, region, f"{title}，包含政务云、安全、双活容灾与实施交付。", title, '{"structured_fields":{"category":"政务云"}}'),
            )
        conn.execute(
            "INSERT INTO bid_plan_tasks(id, notice_id, task_key, title, milestone_type, status, completed_at) VALUES ('memory-task-won', 'history-won', 'security-response', '完成安全响应章节复核', 'document', 'completed', datetime('now'))"
        )


def _outcome(settings: Settings, notice_id: str, result: str, lessons: str) -> None:
    record_outcome(
        settings,
        notice_id,
        {"result": result, "reason_code": "technical_fit" if result == "won" else "partner", "summary": "项目结果已经由负责人核验。", "lessons": lessons, "evidence_url": f"https://example.com/{notice_id}/result"},
        actor="ou_owner" if notice_id != "other-secret" else "ou_other",
    )


if __name__ == "__main__":
    unittest.main()
