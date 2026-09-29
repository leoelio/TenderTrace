from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tendertrace.config import Settings
from tendertrace.company_due_diligence import (
    add_company_evidence,
    add_authorized_external_evidence,
    add_company_relationship,
    ask_company_due_diligence,
    aggregate_existing_company_data,
    confirm_company_identity,
    confirm_company_risk_signal,
    create_company_due_diligence_task,
    create_company_entity,
    evaluate_company_risks,
    get_company_evidence,
    get_company_due_diligence_profile,
    latest_verified_company_snapshot,
    list_company_entities,
    resolve_company_candidates,
    review_company_evidence,
    save_company_due_diligence_snapshot,
    submit_due_diligence_review,
    subscribe_company_changes,
    verify_company_subject_from_official_evidence,
)
from tendertrace.db import SCHEMA_VERSION, connection, database_health, init_db
from tendertrace.integrations.feishu_company_due_diligence import (
    sync_company_due_diligence_task,
)
from tendertrace.organization_memory import create_workspace
from tendertrace.app import api as api_module


class CompanyDueDiligenceSchemaTests(unittest.TestCase):
    def test_schema_56_creates_isolated_due_diligence_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            health = database_health(settings)
            with connection(settings) as conn:
                tables = {
                    str(row["name"])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

        self.assertGreaterEqual(SCHEMA_VERSION, 56)
        self.assertIn(SCHEMA_VERSION, health["schema_versions"])
        self.assertTrue(
            {
                "company_entities",
                "company_aliases",
                "company_evidence",
                "company_risk_signals",
                "company_relationships",
                "due_diligence_reviews",
                "company_due_diligence_tasks",
                "company_change_subscriptions",
                "company_due_diligence_snapshots",
                "company_due_diligence_audit_events",
                "company_due_diligence_answers",
            }.issubset(tables)
        )

    def test_credit_code_is_unique_only_inside_one_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            with connection(settings) as conn:
                conn.execute(
                    """
                    INSERT INTO company_entities(
                        id, workspace_id, legal_name, unified_credit_code, created_by
                    ) VALUES ('a', 'workspace-a', '甲公司', '91110000123456789X', 'test')
                    """
                )
                conn.execute(
                    """
                    INSERT INTO company_entities(
                        id, workspace_id, legal_name, unified_credit_code, created_by
                    ) VALUES ('b', 'workspace-b', '甲公司', '91110000123456789X', 'test')
                    """
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        """
                        INSERT INTO company_entities(
                            id, workspace_id, legal_name, unified_credit_code, created_by
                        ) VALUES ('c', 'workspace-a', '同码公司', '91110000123456789X', 'test')
                        """
                    )


class CompanyIdentityResolutionTests(unittest.TestCase):
    def test_same_name_entities_remain_candidates_until_human_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_identity")
            first = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="华兴科技有限公司",
                region="北京",
                legal_representative="张明",
                actor="ou_member",
            )
            second = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="华兴科技有限公司",
                region="上海",
                legal_representative="李静",
                actor="ou_member",
            )

            unresolved = resolve_company_candidates(
                settings,
                workspace_id=workspace,
                query="华兴科技有限公司",
                actor="ou_member",
            )

            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(unresolved["resolution"], "needs_confirmation")
            self.assertEqual(len(unresolved["candidates"]), 2)
            self.assertTrue(
                all(item["requires_human_confirmation"] for item in unresolved["candidates"])
            )

    def test_credit_code_exact_match_is_confirmed_and_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_credit")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="成方金融科技有限公司",
                actor="ou_member",
            )
            confirm_company_identity(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                unified_credit_code="91110000123456789X",
                reason="核对企业营业执照原件",
            )
            other = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="同名候选主体",
                actor="ou_member",
            )

            resolved = resolve_company_candidates(
                settings,
                workspace_id=workspace,
                query="",
                unified_credit_code="91110000123456789X",
                actor="ou_member",
            )

            self.assertEqual(resolved["resolution"], "confirmed")
            self.assertEqual(len(resolved["candidates"]), 1)
            self.assertFalse(resolved["candidates"][0]["requires_human_confirmation"])
            with self.assertRaisesRegex(ValueError, "already belongs"):
                confirm_company_identity(
                    settings,
                    str(other["id"]),
                    workspace_id=workspace,
                    actor="ou_owner",
                    unified_credit_code="91110000123456789X",
                    reason="错误地试图复用代码",
                )

    def test_only_owner_can_confirm_and_workspace_data_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace_a = _workspace(settings, "oc_a")
            workspace_b = _workspace(settings, "oc_b")
            entity = create_company_entity(
                settings,
                workspace_id=workspace_a,
                legal_name="隔离测试有限公司",
                legal_representative="王强",
                actor="ou_member",
            )

            with self.assertRaises(PermissionError):
                confirm_company_identity(
                    settings,
                    str(entity["id"]),
                    workspace_id=workspace_a,
                    actor="ou_member",
                    unified_credit_code="91310000123456789Y",
                    reason="普通成员无权确认",
                )
            with self.assertRaises(PermissionError):
                list_company_entities(
                    settings,
                    workspace_id=workspace_a,
                    actor="ou_outsider",
                )
            self.assertEqual(
                list_company_entities(
                    settings,
                    workspace_id=workspace_b,
                    actor="admin",
                    query="隔离测试",
                ),
                [],
            )

    def test_existing_project_data_is_aggregated_with_traceable_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_aggregate")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="华云服务器有限公司",
                actor="ou_member",
            )
            with connection(settings) as conn:
                conn.execute(
                    """
                    INSERT INTO notices(
                        id, source_site, source_url, canonical_url, title,
                        publish_time, purchaser, content_text
                    ) VALUES (
                        'notice-award', 'ggzy', 'https://example.cn/award',
                        'https://example.cn/award', '服务器采购成交公告',
                        '2026-09-01', '采购单位',
                        '中标供应商：华云服务器有限公司，中标金额100万元'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO opportunity_outcomes(
                        notice_id, result, reason_code, winner_name, summary,
                        lessons, evidence_url, recorded_by, finalized_at
                    ) VALUES (
                        'notice-award', 'won', 'technical_fit', '华云服务器有限公司',
                        '华云服务器有限公司中标服务器采购项目', '按期交付',
                        'https://example.cn/award', 'test', '2026-09-02'
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO organization_memories(
                        id, workspace_id, memory_type, title, content, source_type,
                        content_hash, created_by
                    ) VALUES (
                        'memory-1', ?, 'customer_signal', '合作记录',
                        '华云服务器有限公司曾完成联合测试', 'manual', 'hash-1', 'test'
                    )
                    """,
                    (workspace,),
                )

            result = aggregate_existing_company_data(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
            )

            self.assertEqual(result["imported_count"], 3)
            self.assertEqual(
                {item["source_type"] for item in result["evidence"]},
                {"notice", "award_result", "organization_memory"},
            )
            self.assertTrue(all(item["subject_match_basis"] for item in result["evidence"]))
            self.assertIn("未调用外部受限数据源", result["policy"])

    def test_sensitive_manual_evidence_requires_redacted_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_manual")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="人工材料测试公司",
                actor="ou_member",
            )

            with self.assertRaisesRegex(ValueError, "redacted_content"):
                add_company_evidence(
                    settings,
                    str(entity["id"]),
                    workspace_id=workspace,
                    actor="ou_member",
                    evidence_type="cooperation_record",
                    title="历史合作合同",
                    content_text="联系人手机号13800138000",
                    sensitive=True,
                )

    def test_risks_facts_and_missing_information_are_separate_and_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_risk")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="风险解释测试公司",
                actor="ou_member",
            )
            risk_evidence = add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                evidence_type="administrative_penalty",
                title="行政处罚决定",
                content_text="2026年8月因未按要求报送材料受到行政处罚，整改状态待核验。",
                source_type="manual_upload",
                source_name="法务上传",
                source_url="https://example.cn/penalty/1",
                occurred_at="2026-08-01",
                confidence=85,
            )
            add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                evidence_type="award_result",
                title="历史中标结果",
                content_text="该公司于2026年7月中标同类服务器项目。",
                source_type="award_result",
                source_name="公共资源交易公告",
                source_url="https://example.cn/award/1",
                occurred_at="2026-07-01",
                confidence=95,
            )

            result = evaluate_company_risks(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
            )

            self.assertFalse(result["has_opaque_overall_score"])
            self.assertEqual(len(result["risks"]), 1)
            self.assertEqual(result["risks"][0]["evidence_id"], risk_evidence["id"])
            self.assertTrue(result["risks"][0]["risk_interpretation"])
            self.assertTrue(result["risks"][0]["business_impact"])
            self.assertTrue(result["risks"][0]["due_diligence_question"])
            self.assertTrue(result["risks"][0]["mitigation"])
            self.assertEqual(len(result["facts"]), 1)
            self.assertGreaterEqual(len(result["missing"]), 4)
            self.assertTrue(
                all("不代表负面事实" in item["risk_interpretation"] for item in result["missing"])
            )

    def test_external_evidence_requires_lawful_access_metadata_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_external")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="外部证据测试公司",
                actor="ou_member",
            )

            evidence = add_authorized_external_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                evidence_type="operating_status",
                title="官方经营状态快照",
                content_text="主体状态：存续；查询时间：2026-09-29。",
                source_type="official_api",
                source_name="官方主体登记接口",
                source_url="https://example.gov.cn/api/company/1",
                source_license="official-open-api-v1",
                access_frequency="daily",
                occurred_at="2026-09-29",
                confidence=98,
            )

            self.assertEqual(evidence["access_frequency"], "daily")
            self.assertEqual(len(evidence["snapshot_sha256"]), 64)
            self.assertEqual(evidence["access_policy"], "authorized_interface")
            with self.assertRaises(ValueError):
                add_authorized_external_evidence(
                    settings,
                    str(entity["id"]),
                    workspace_id=workspace,
                    actor="ou_member",
                    evidence_type="judicial_case",
                    title="不合规抓取",
                    content_text="测试",
                    source_type="browser_scraper",
                    source_name="受限站点",
                    source_url="https://example.cn/restricted",
                    source_license="none",
                    access_frequency="hourly",
                )

    def test_official_subject_verification_requires_exact_code_and_official_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_verify")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="官方核验测试公司",
                actor="ou_member",
            )
            evidence = add_authorized_external_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                evidence_type="subject_registration",
                title="官方主体登记快照",
                content_text="官方核验测试公司，统一社会信用代码：91110000123456789X，状态：存续。",
                source_type="official_public_snapshot",
                source_name="官方登记公示",
                source_url="https://example.gov.cn/company/official",
                source_license="official-public-information",
                access_frequency="on_demand",
            )

            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_company_subject_from_official_evidence(
                    settings,
                    str(entity["id"]),
                    workspace_id=workspace,
                    actor="ou_owner",
                    evidence_id=str(evidence["id"]),
                    unified_credit_code="91310000123456789Y",
                    reason="测试错误代码",
                )
            verified = verify_company_subject_from_official_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                evidence_id=str(evidence["id"]),
                unified_credit_code="91110000123456789X",
                reason="负责人核对官方登记快照",
            )
            self.assertEqual(verified["identity_status"], "confirmed")
            self.assertEqual(verified["verification_status"], "official_verified")

    def test_expired_or_withdrawn_evidence_cannot_support_deterministic_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_validity")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="有效性测试公司",
                actor="ou_member",
            )
            expired = add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                evidence_type="judicial_case",
                title="已过期案件核验",
                content_text="旧案件状态快照。",
                valid_until="2025-12-31",
            )
            current = add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                evidence_type="administrative_penalty",
                title="当前处罚记录",
                content_text="处罚整改状态待核验。",
                valid_until="2027-12-31",
            )
            review_company_evidence(
                settings,
                str(expired["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                status="verified",
                reason="核过旧材料",
            )
            review_company_evidence(
                settings,
                str(current["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                status="verified",
                reason="核对有效材料",
            )
            evaluated = evaluate_company_risks(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
            )

            self.assertEqual(len(evaluated["risks"]), 1)
            self.assertTrue(evaluated["risks"][0]["deterministic"])
            signal_id = str(evaluated["risks"][0]["id"])
            confirm_company_risk_signal(
                settings,
                signal_id,
                workspace_id=workspace,
                actor="ou_owner",
                status="active",
                reason="人工确认风险仍有效",
            )
            review_company_evidence(
                settings,
                str(current["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                status="withdrawn",
                reason="来源撤回原记录",
            )
            rerun = evaluate_company_risks(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
            )
            retained = next(item for item in rerun["risks"] if item["id"] == signal_id)
            self.assertEqual(retained["signal_status"], "invalidated")
            self.assertFalse(retained["deterministic"])

    def test_follow_up_answer_cites_evidence_and_exposes_gaps_and_mitigation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_question")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="合同约束测试公司",
                actor="ou_member",
            )
            evidence = add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                evidence_type="administrative_penalty",
                title="有效处罚记录",
                content_text="因交付材料不符合监管要求受到处罚，整改证明待复核。",
                source_url="https://example.cn/penalty/current",
                valid_until="2027-12-31",
            )
            review_company_evidence(
                settings,
                str(evidence["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                status="verified",
                reason="法务已核对处罚决定",
            )
            evaluate_company_risks(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
            )

            answer = ask_company_due_diligence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                question="如果合作，合同里最需要约束什么？",
            )

            self.assertIn(str(evidence["id"]), answer["evidence_ids"])
            self.assertIn(f"[企业证据:{evidence['id']}]", answer["answer"])
            self.assertTrue(answer["missing_items"])
            self.assertTrue(answer["worst_impact"])
            self.assertIn("合同", answer["mitigation"])

    def test_due_diligence_task_syncs_to_feishu_with_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_task")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="任务同步测试公司",
                actor="ou_member",
            )
            task = create_company_due_diligence_task(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_member",
                title="核验处罚整改证明",
                question="处罚是否已经履行并完成整改？",
                task_type="legal",
                assignee_open_id="ou_owner",
                due_at="2026-10-10T18:00:00+08:00",
            )
            fake = _FakeFeishuClient()

            synced = sync_company_due_diligence_task(
                settings,
                str(task["id"]),
                client=fake,  # type: ignore[arg-type]
            )
            reused = sync_company_due_diligence_task(
                settings,
                str(task["id"]),
                client=fake,  # type: ignore[arg-type]
            )

            self.assertEqual(synced["status"], "created")
            self.assertEqual(reused["status"], "reused")
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(synced["task_guid"], "task-dd-001")
            self.assertEqual(synced["receipt"]["data"]["task"]["guid"], "task-dd-001")

    def test_sensitive_evidence_is_redacted_for_members_and_access_is_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_sensitive")
            other_workspace = _workspace(settings, "oc_sensitive_other")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="敏感材料测试公司",
                actor="ou_member",
            )
            evidence = add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                evidence_type="cooperation_record",
                title="商业合作访谈",
                content_text="联系人张三，手机号13800138000，合同金额500万元。",
                redacted_content="联系人张*，手机号1**********，合同金额已脱敏。",
                sensitive=True,
            )

            member_view = get_company_evidence(
                settings,
                str(evidence["id"]),
                workspace_id=workspace,
                actor="ou_member",
            )
            owner_view = get_company_evidence(
                settings,
                str(evidence["id"]),
                workspace_id=workspace,
                actor="ou_owner",
            )

            self.assertNotIn("13800138000", member_view["content_text"])
            self.assertIn("13800138000", owner_view["content_text"])
            with self.assertRaises(LookupError):
                get_company_evidence(
                    settings,
                    str(evidence["id"]),
                    workspace_id=other_workspace,
                    actor="ou_owner",
                )
            with connection(settings) as conn:
                audit_count = conn.execute(
                    """
                    SELECT count(*) FROM company_due_diligence_audit_events
                    WHERE entity_id = ? AND action = 'sensitive_company_evidence_accessed'
                    """,
                    (entity["id"],),
                ).fetchone()[0]
            self.assertEqual(audit_count, 2)

    def test_profile_relationship_review_subscription_and_offline_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_profile")
            entity = create_company_entity(
                settings,
                workspace_id=workspace,
                legal_name="画像验收测试公司",
                actor="ou_member",
            )
            evidence = add_company_evidence(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                evidence_type="award_result",
                title="历史中标公告",
                content_text="画像验收测试公司中标服务器项目。",
                source_url="https://example.cn/award/profile",
            )
            review_company_evidence(
                settings,
                str(evidence["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                status="verified",
                reason="核对公告原文",
            )
            evaluate_company_risks(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
            )
            relation = add_company_relationship(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                related_label="服务器采购项目",
                relationship_type="award",
                basis_type="factual",
                confidence=95,
                evidence_id=str(evidence["id"]),
                related_object_type="project",
                related_object_id="project-server-001",
            )
            review = submit_due_diligence_review(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                recommendation="conditional",
                reason="履约事实可核验，但其他维度仍需补齐",
                valid_until="2027-03-31",
                conditions=["补充司法合规证明", "合同设置持续合规条款"],
            )
            subscription = subscribe_company_changes(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                event_types=["judicial", "operations"],
            )
            profile = get_company_due_diligence_profile(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
            )
            snapshot = save_company_due_diligence_snapshot(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
                verified=True,
            )
            offline = latest_verified_company_snapshot(
                settings,
                str(entity["id"]),
                workspace_id=workspace,
                actor="ou_owner",
            )

            self.assertEqual(profile["summary"]["recommendation"], "conditional")
            self.assertEqual(profile["current_review"]["id"], review["id"])
            self.assertEqual(profile["relationships"][0]["id"], relation["id"])
            self.assertEqual(profile["relationship_graph"]["edges"][0]["basis_type"], "factual")
            self.assertEqual(subscription["event_types"], ["judicial", "operations"])
            self.assertTrue(snapshot["verified"])
            self.assertTrue(offline["offline_ready"])
            self.assertEqual(offline["state_hash"], snapshot["state_hash"])

    def test_api_exposes_company_profile_evaluation_question_and_snapshot(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            workspace = _workspace(settings, "oc_api")
            with patch.object(api_module.Settings, "load", return_value=settings):
                with TestClient(api_module.create_app()) as client:
                    created = client.post(
                        f"/api/organization/workspaces/{workspace}/companies",
                        json={"legal_name": "API验收公司", "region": "北京", "actor": "ou_member"},
                    )
                    entity_id = created.json()["entity"]["id"]
                    added = client.post(
                        f"/api/organization/workspaces/{workspace}/companies/{entity_id}/evidence",
                        json={
                            "evidence_type": "administrative_penalty",
                            "title": "API处罚证据",
                            "content_text": "处罚状态待确认。",
                            "actor": "ou_owner",
                        },
                    )
                    evaluated = client.post(
                        f"/api/organization/workspaces/{workspace}/companies/{entity_id}/evaluate",
                        json={"actor": "ou_owner"},
                    )
                    asked = client.post(
                        f"/api/organization/workspaces/{workspace}/companies/{entity_id}/ask",
                        json={"actor": "ou_member", "question": "合同需要约束什么？"},
                    )
                    profile = client.get(
                        f"/api/organization/workspaces/{workspace}/companies/{entity_id}",
                        params={"actor": "ou_owner"},
                    )
                    snapshot = client.post(
                        f"/api/organization/workspaces/{workspace}/companies/{entity_id}/snapshots",
                        json={"actor": "ou_owner", "verified": True},
                    )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(added.status_code, 200)
        self.assertEqual(evaluated.status_code, 200)
        self.assertEqual(asked.status_code, 200)
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(profile.json()["entity"]["legal_name"], "API验收公司")
        self.assertTrue(snapshot.json()["offline_ready"])


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\n"
        "TENDERTRACE_SCHEDULER_ENABLED=false\n"
        "FEISHU_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _workspace(settings: Settings, chat_id: str) -> str:
    return create_workspace(
        settings,
        name=f"测试空间 {chat_id}",
        feishu_chat_id=chat_id,
        members=[
            {"open_id": "ou_owner", "name": "负责人", "role": "owner"},
            {"open_id": "ou_member", "name": "成员", "role": "member"},
        ],
        actor="admin",
    ).id


class _FakeFeishuClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_task(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"code": 0, "data": {"task": {"guid": "task-dd-001"}}}


if __name__ == "__main__":
    unittest.main()
