from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest

from tendertrace.capability_matching import upsert_capability
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.evidence_microscope import _comparison, build_evidence_microscope, review_evidence
from tendertrace.notice_changes import record_notice_revision
from tendertrace.opportunity_requirements import upsert_requirement


class EvidenceMicroscopeTests(unittest.TestCase):
    def test_comparison_does_not_report_two_values_in_one_source_as_cross_source_conflict(self) -> None:
        comparison = _comparison(
            [
                {
                    "id": "source-a",
                    "quote": "FusionOS 最低内存4GB，建议8GB。",
                    "verified_status": "verified",
                },
                {
                    "id": "source-b",
                    "quote": "该材料只描述ARM兼容性。",
                    "verified_status": "verified",
                },
            ]
        )

        self.assertEqual(comparison["status"], "aligned")
        self.assertFalse(comparison["items"][0]["conflict"])

    def test_builds_traceable_claims_from_tender_and_enterprise_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            requirement_id, capability_id = _insert_requirement_and_capability(settings)
            _insert_match(settings, requirement_id, capability_id, verdict="supported")

            payload = build_evidence_microscope(
                settings,
                "notice-evidence-1",
                claim_type="capability_match",
                claim_key="match-1",
            )

        assert payload is not None
        self.assertTrue(payload["summary"]["audit_complete"])
        self.assertEqual(payload["summary"]["definitive_without_valid_evidence"], 0)
        selected = next(item for item in payload["claims"] if item["id"] == payload["selected_claim_id"])
        self.assertEqual(selected["claim_type"], "capability_match")
        self.assertEqual({item["source_type"] for item in selected["evidence"]}, {"pdf", "enterprise_material"})
        tender = next(item for item in selected["evidence"] if item["source_type"] == "pdf")
        self.assertEqual(tender["page_number"], 12)
        self.assertTrue(any(item["kind"] == "parameter" for item in tender["highlights"]))
        self.assertIn(selected["comparison"]["status"], {"aligned", "different"})
        self.assertTrue(any(item["claim_type"] == "score" for item in payload["claims"]))

    def test_human_review_is_append_only_and_survives_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            payload = build_evidence_microscope(settings, "notice-evidence-1")
            assert payload is not None
            fact = next(item for item in payload["claims"] if item["claim_type"] == "fact" and item["claim_key"] == "budget")
            evidence_id = fact["evidence"][0]["id"]

            reviewed = review_evidence(
                settings,
                "notice-evidence-1",
                evidence_id,
                action="confirm",
                actor="张评审",
                reason="已与公告第 1 页预算字段逐字核对",
            )
            rebuilt = build_evidence_microscope(settings, "notice-evidence-1")

        assert rebuilt is not None
        source = next(
            source
            for claim in rebuilt["claims"]
            for source in claim["evidence"]
            if source["id"] == evidence_id
        )
        self.assertEqual(source["verified_status"], "verified")
        self.assertEqual(source["confirmed_by"], "张评审")
        self.assertTrue(any(event["action"] == "confirm" for event in reviewed["audit_events"]))

    def test_notice_revision_expires_old_evidence_and_requires_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            first = build_evidence_microscope(settings, "notice-evidence-1")
            assert first is not None
            with connection(settings) as conn:
                fields = {"structured_fields": {"project_no": "TT-2026-001", "budget": "600万元", "bid_deadline": (date.today() + timedelta(days=20)).isoformat()}}
                conn.execute(
                    "UPDATE notices SET content_text = ?, fields_json = ?, updated_at = datetime('now') WHERE id = ?",
                    ("项目预算调整为600万元，技术参数要求内存不低于64GB。", json.dumps(fields, ensure_ascii=False), "notice-evidence-1"),
                )
                revision = record_notice_revision(
                    conn,
                    notice_id="notice-evidence-1",
                    before={"budget": "500万元", "content_text": "项目预算为500万元，技术参数要求内存不低于64GB。"},
                    after={"budget": "600万元", "content_text": "项目预算调整为600万元，技术参数要求内存不低于64GB。"},
                )
            self.assertIsNotNone(revision)

            changed = build_evidence_microscope(settings, "notice-evidence-1")

        assert changed is not None
        budget = next(item for item in changed["claims"] if item["claim_type"] == "fact" and item["claim_key"] == "budget")
        self.assertEqual(budget["status"], "recheck")
        self.assertEqual(budget["conclusion"], "600万元")
        self.assertTrue(any(item["verified_status"] == "expired" for item in budget["evidence"]))
        self.assertTrue(any(item["verified_status"] == "pending" for item in budget["evidence"]))
        self.assertTrue(any(event["action"] == "source_invalidated" for event in changed["audit_events"]))

    def test_multi_agent_disagreement_keeps_each_rationale_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            requirement_id, capability_id = _insert_requirement_and_capability(settings)
            _insert_match(settings, requirement_id, capability_id, verdict="gap")
            alternative = upsert_capability(
                settings,
                capability_key="CAP-SERVER-02",
                title="待确认的升级方案",
                capability_type="product",
                evidence_text="供应商说明可升级至64GB，但正式规格书待补。",
                source_url="https://example.com/upgrade.html",
                source_locator="产品说明页 / 升级选项",
                verification_status="verified",
                owner="产品部",
                actor="test",
            )
            with connection(settings) as conn:
                conn.execute(
                    """
                    INSERT INTO requirement_capability_matches(
                        id, notice_id, requirement_id, capability_id, verdict,
                        confidence, rationale, status, decided_by, decision_note, decided_at
                    ) VALUES ('match-2', 'notice-evidence-1', ?, ?, 'needs_evidence', 76,
                              '存在升级说明，但正式规格书待补。', 'confirmed', '评审员', '逐项核验', datetime('now'))
                    """,
                    (requirement_id, alternative.id),
                )
                conn.execute(
                    "INSERT INTO requirement_review_cases(id, notice_id, requirement_id, reviewer_role, reason) VALUES ('review-1', ?, ?, 'technical', 'capability_gap')",
                    ("notice-evidence-1", requirement_id),
                )
                conn.executemany(
                    """
                    INSERT INTO requirement_review_opinions(
                        id, review_id, notice_id, requirement_id, agent_role, decision,
                        confidence, rationale, model_status
                    ) VALUES (?, 'review-1', ?, ?, ?, ?, ?, ?, 'ok')
                    """,
                    [
                        ("opinion-1", "notice-evidence-1", requirement_id, "technical", "reject", 91, "企业材料仅承诺32GB，低于招标64GB。"),
                        ("opinion-2", "notice-evidence-1", requirement_id, "commercial", "escalate", 72, "存在升级路径，但正式规格书和报价待确认。"),
                    ],
                )

            payload = build_evidence_microscope(settings, "notice-evidence-1")

        assert payload is not None
        self.assertEqual(len(payload["disagreements"]), 1)
        opinions = payload["disagreements"][0]["opinions"]
        self.assertEqual({item["decision"] for item in opinions}, {"escalate", "reject"})
        self.assertTrue(all(item["evidence"] for item in opinions))
        enterprise_sets = [
            {source["source_id"] for source in item["evidence"] if source["source_type"] == "enterprise_material"}
            for item in opinions
        ]
        self.assertNotEqual(enterprise_sets[0], enterprise_sets[1])

    def test_api_returns_microscope_and_records_review(self) -> None:
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
                response = client.get("/api/opportunities/notice-evidence-1/evidence-microscope?claim_type=fact&claim_key=budget")
                evidence_id = response.json()["claims"][0]["evidence"][0]["id"]
                reviewed = client.post(
                    f"/api/opportunities/notice-evidence-1/evidence-microscope/{evidence_id}/review",
                    json={"action": "confirm", "actor": "API评审", "reason": "现场核对"},
                )
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reviewed.status_code, 200)
        self.assertTrue(reviewed.json()["audit_events"])


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    fields = {
        "structured_fields": {
            "project_no": "TT-2026-001",
            "budget": "500万元",
            "bid_deadline": (date.today() + timedelta(days=20)).isoformat(),
        }
    }
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, purchaser,
                publish_time, region, content_text, core_content, fields_json,
                snapshot_sha256, updated_at, last_seen_at
            ) VALUES (?, 'ccgp', ?, ?, ?, ?, ?, '北京', ?, ?, ?, 'notice-hash-v1', datetime('now'), datetime('now'))
            """,
            (
                "notice-evidence-1",
                "https://example.com/tender.html",
                "https://example.com/tender.html",
                "数据中心服务器采购项目",
                "示例采购中心",
                date.today().isoformat(),
                "项目预算为500万元，技术参数要求内存不低于64GB，投标人必须提供认证材料。",
                "采购服务器并完成部署。",
                json.dumps(fields, ensure_ascii=False),
            ),
        )


def _insert_requirement_and_capability(settings: Settings) -> tuple[str, str]:
    requirement = upsert_requirement(
        settings,
        notice_id="notice-evidence-1",
        requirement_key="TECH-01",
        requirement_type="qualification",
        title="服务器内存不少于64GB",
        evidence_text="技术参数要求内存不低于64GB，投标人必须提供认证材料。",
        source_url="https://example.com/spec.pdf",
        source_locator="招标文件.pdf 第12页 第3.2节",
        mandatory=True,
        confidence=98,
        status="confirmed",
        actor="test",
    )
    capability = upsert_capability(
        settings,
        capability_key="CAP-SERVER-01",
        title="服务器产品规格",
        capability_type="product",
        evidence_text="标准配置内存64GB，可扩展至256GB。",
        source_url="https://example.com/product.docx",
        source_locator="产品规格书.docx 第8段",
        verification_status="verified",
        owner="产品部",
        valid_until="",
        actor="test",
    )
    return requirement.id, capability.id


def _insert_match(settings: Settings, requirement_id: str, capability_id: str, *, verdict: str) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO requirement_capability_matches(
                id, notice_id, requirement_id, capability_id, verdict,
                confidence, rationale, status, decided_by, decision_note, decided_at
            ) VALUES ('match-1', 'notice-evidence-1', ?, ?, ?, 92, ?, 'confirmed', '评审员', '逐项核验', datetime('now'))
            """,
            (
                requirement_id,
                capability_id,
                verdict,
                "企业材料与招标参数一致。" if verdict == "supported" else "企业材料参数低于招标要求。",
            ),
        )


if __name__ == "__main__":
    unittest.main()
