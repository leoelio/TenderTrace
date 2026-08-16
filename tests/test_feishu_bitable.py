from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.delivery.feishu_bitable import (
    REQUIRED_FIELDS,
    check_feishu_bitable,
    sync_notices_to_bitable,
    update_opportunity_facts_in_bitable,
    update_opportunity_team_in_bitable,
    update_opportunity_workflow_in_bitable,
)
from tendertrace.integrations.feishu_leads import (
    import_partner_leads,
    list_feishu_lead_import_runs,
)
from tendertrace.source_verification import SourceVerification
from tendertrace.db import connection, init_db


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self.payload


class FakeFeishuClient:
    created_records: list[dict] = []
    updated_records: list[tuple[str, dict]] = []
    created_fields: list[str] = []

    def __init__(self, timeout: float, **_: object) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, *, json=None, headers=None):
        if url.endswith("/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "tenant-token"})
        if url.endswith("/fields"):
            field_name = json["field_name"]
            self.created_fields.append(field_name)
            return FakeResponse(
                {
                    "code": 0,
                    "data": {"field": {"field_id": f"fld-{field_name}", "field_name": field_name}},
                }
            )
        if url.endswith("/records/batch_create"):
            records = json["records"]
            self.created_records.extend(records)
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "records": [
                            {"record_id": f"rec-{index}"} for index, _ in enumerate(records)
                        ]
                    },
                }
            )
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url: str, *, params=None, headers=None):
        if url.endswith("/tables"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "table_id": "tbl_test",
                                "name": "招标机会",
                            }
                        ]
                    },
                }
            )
        if url.endswith("/fields"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {"field_id": f"fld-{name}", "field_name": name, "type": 1}
                            for name in REQUIRED_FIELDS
                        ]
                    },
                }
            )
        if url.endswith("/records"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "record_id": "rec-existing",
                                "fields": {
                                    "项目指纹": "ccgp:existing",
                                    "公告ID": "existing",
                                },
                            }
                        ],
                        "has_more": False,
                    },
                }
            )
        raise AssertionError(f"unexpected GET {url}")

    def put(self, url: str, *, json=None, headers=None):
        self.updated_records.append((url, json["fields"]))
        return FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-existing"}}})


class MissingFieldClient(FakeFeishuClient):
    def get(self, url: str, *, params=None, headers=None):
        if url.endswith("/fields"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {"items": [{"field_id": "fld-title", "field_name": "标题", "type": 1}]},
                }
            )
        return super().get(url, params=params, headers=headers)


class PartnerLeadClient(FakeFeishuClient):
    def get(self, url: str, *, params=None, headers=None):
        if url.endswith("/records"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "record_id": "rec-partner-1",
                                "fields": {
                                    "标题": "合作伙伴提交的数据中心服务器采购",
                                    "来源链接": "https://partner.example.com/tender/1",
                                    "来源": "华东合作伙伴",
                                    "状态": "伙伴提交",
                                    "线索正文": "采购机架服务器及三年维保服务。",
                                    "伙伴提交人": "李四",
                                    "地区": "上海",
                                    "发布时间": "2026-08-15",
                                    "采购人": "示例采购单位",
                                    "附件链接": "https://partner.example.com/spec.pdf",
                                },
                            },
                            {
                                "record_id": "rec-synced",
                                "fields": {
                                    "标题": "系统已同步记录",
                                    "来源链接": "https://example.com/existing",
                                    "状态": "新增",
                                    "公告ID": "existing",
                                    "项目指纹": "ccgp:existing",
                                },
                            },
                        ],
                        "has_more": False,
                    },
                }
            )
        return super().get(url, params=params, headers=headers)


class UnsafePartnerLeadClient(FakeFeishuClient):
    def get(self, url: str, *, params=None, headers=None):
        if url.endswith("/records"):
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "record_id": "rec-unsafe",
                                "fields": {
                                    "标题": "不安全来源",
                                    "来源链接": "http://127.0.0.1/admin",
                                    "状态": "待导入",
                                },
                            }
                        ],
                        "has_more": False,
                    },
                }
            )
        return super().get(url, params=params, headers=headers)


class FeishuBitableTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeFeishuClient.created_records = []
        FakeFeishuClient.updated_records = []
        FakeFeishuClient.created_fields = []

    def test_check_skips_when_channel_settings_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings.load(Path(tmp))

            result = check_feishu_bitable(settings, http_client_factory=FakeFeishuClient)

        self.assertEqual(result.status, "skipped")
        self.assertIn("TENDERTRACE_FEISHU_APP_ID", result.message)

    def test_check_passes_when_required_fields_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))

            result = check_feishu_bitable(settings, http_client_factory=FakeFeishuClient)

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.table_id, "tbl_test")
        self.assertEqual(result.table_name, "招标机会")
        self.assertEqual(result.record_count, 1)
        self.assertEqual(result.missing_fields, ())

    def test_check_can_create_missing_fields_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))

            result = check_feishu_bitable(
                settings,
                ensure_fields=True,
                http_client_factory=MissingFieldClient,
            )

        self.assertEqual(result.status, "warn")
        self.assertIn("地区", result.created_fields)
        self.assertIn("项目指纹", result.missing_fields)

    def test_sync_creates_new_records_and_updates_existing_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = _settings(root)
            outbox = root / "outbox" / "report.docx"
            outbox.parent.mkdir(parents=True, exist_ok=True)
            outbox.write_bytes(b"docx")

            result = sync_notices_to_bitable(
                settings,
                notices=[
                    _notice("existing", cluster_key="ccgp:existing"),
                    _notice("new", cluster_key="ccgp:new"),
                ],
                bidql={"topic": {"core": ["服务器"]}},
                query="最近1个月上海服务器招标信息",
                run_id="run-1",
                outbox_path=outbox,
                synced_at=datetime(2026, 8, 6, 9, 0),
                http_client_factory=FakeFeishuClient,
            )

        self.assertEqual(result.status, "sent")
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.updated_count, 1)
        payload = result.to_dict()
        self.assertNotIn("app_token", payload)
        self.assertTrue(payload["app_token_configured"])
        self.assertNotIn("base_test", str(payload))
        created = FakeFeishuClient.created_records[0]["fields"]
        self.assertEqual(created["标题"], "new title")
        self.assertEqual(created["关键词"], "服务器")
        self.assertEqual(created["状态"], "新增")
        self.assertEqual(created["项目指纹"], "ccgp:new")
        self.assertEqual(created["公告ID"], "new")
        self.assertEqual(created["机会等级"], "B · 重点观察")
        self.assertEqual(created["机会评分"], "72")
        self.assertIn("机会点负责人", created["跟进建议"])
        self.assertIn("/api/outbox/report.docx", created["Word 报告"])
        self.assertEqual(created["市场价格位置"], "高于同品类历史中位数")
        self.assertEqual(created["市场样本数"], "8")
        self.assertIn("上海样例科技有限公司", created["竞争情报"])
        self.assertIn("结果公告原文", created["竞争证据"])
        self.assertEqual(created["历史竞争者"], "上海样例科技有限公司（2 次）")
        self.assertEqual(created["需求覆盖率"], "63/100 · 5/8 项")
        self.assertEqual(created["需求待核对"], "评分规则、安全要求")
        self.assertIn("获取评分办法", created["需求优化建议"])
        updated = FakeFeishuClient.updated_records[0][1]
        self.assertIn("Word 报告", updated)
        self.assertIn("机会评分", updated)
        self.assertIn("建议策略", updated)
        self.assertIn("竞争情报", updated)
        self.assertIn("需求覆盖率", updated)

    def test_workflow_update_uses_notice_id_and_preserves_notice_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))

            result = update_opportunity_workflow_in_bitable(
                settings,
                notice_id="find_tender:existing",
                workflow={
                    "stage": "qualifying",
                    "stage_label": "机会确认",
                    "owner_name": "张三",
                    "next_action": "确认预算",
                    "feishu_task_guid": "task-guid",
                    "feishu_task_status": "completed",
                    "feishu_task_completed_at": "2026-08-15T10:00:00+00:00",
                    "feishu_task_synced_at": "2026-08-15T10:05:00+00:00",
                    "feishu_event_id": "event-id",
                    "qualification_score": 82,
                    "qualification_status": "ready",
                    "decision": "go",
                    "decision_reason": "客户预算与交付资源已确认",
                    "decision_by": "销售经理",
                    "decision_at": "2026-08-15T09:55:00",
                    "decision_sla_status": "overdue",
                    "decision_sla_hours": 24,
                    "decision_wait_hours": 31.5,
                    "decision_due_at": "2026-08-15T09:00:00+00:00",
                    "updated_at": "2026-08-15T10:00:00",
                },
                http_client_factory=FakeFeishuClient,
            )

        self.assertEqual(result.status, "sent")
        fields = FakeFeishuClient.updated_records[0][1]
        self.assertEqual(fields["协同状态"], "机会确认")
        self.assertEqual(fields["机会负责人"], "张三")
        self.assertEqual(fields["飞书任务状态"], "已完成")
        self.assertEqual(fields["飞书任务完成时间"], "2026-08-15T10:00:00+00:00")
        self.assertEqual(fields["资格评分"], "82")
        self.assertEqual(fields["准入状态"], "可决策")
        self.assertEqual(fields["投标决策"], "Go")
        self.assertEqual(fields["决策人"], "销售经理")
        self.assertEqual(fields["决策SLA状态"], "已超时升级")
        self.assertEqual(fields["决策SLA时限"], "24 小时")
        self.assertEqual(fields["决策等待小时"], "31.5")
        self.assertNotIn("标题", fields)

    def test_fact_update_recomputes_business_fields_on_existing_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))

            result = update_opportunity_facts_in_bitable(
                settings,
                notice_id="existing",
                opportunity={
                    "region": "上海市",
                    "purchaser": "上海政府采购中心",
                    "project_no": "SH-2026-0816",
                    "budget": "320 万元",
                    "bid_deadline": "2026-08-30",
                    "fact_overrides": [
                        {
                            "field_name": "budget",
                            "field_label": "预算",
                            "field_value": "320 万元",
                            "updated_at": "2026-08-16T09:30:00+08:00",
                        }
                    ],
                    "intelligence": {
                        "level": "A",
                        "level_label": "优先推进",
                        "score": 91,
                        "scores": {"completeness": 88, "credibility": 93},
                    },
                    "qualification": {"score": 86, "status": "ready"},
                },
                http_client_factory=FakeFeishuClient,
            )

        self.assertEqual(result.status, "sent")
        fields = FakeFeishuClient.updated_records[0][1]
        self.assertEqual(fields["项目编号"], "SH-2026-0816")
        self.assertEqual(fields["事实核验状态"], "已核验 1 项")
        self.assertEqual(fields["事实核验证据"], "")
        self.assertEqual(fields["事实核验备注"], "")
        self.assertEqual(fields["事实核验人"], "")
        self.assertEqual(fields["事实核验摘要"], "预算：320 万元")
        self.assertEqual(fields["机会等级"], "A · 优先推进")
        self.assertEqual(fields["准入状态"], "可决策")
        self.assertNotIn("标题", fields)

    def test_team_update_preserves_notice_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))

            result = update_opportunity_team_in_bitable(
                settings,
                notice_id="existing",
                team={
                    "coverage_score": 67,
                    "missing_roles": ["商务报价"],
                    "members": [
                        {
                            "member_name": "李工",
                            "role_label": "方案技术",
                            "organization_type": "internal",
                        },
                        {
                            "member_name": "王经理",
                            "role_label": "伙伴负责人",
                            "organization_type": "partner",
                            "organization_name": "伙伴科技",
                        },
                    ],
                },
                http_client_factory=FakeFeishuClient,
            )

        self.assertEqual(result.status, "sent")
        fields = FakeFeishuClient.updated_records[0][1]
        self.assertEqual(fields["机会团队"], "李工（方案技术）")
        self.assertEqual(fields["合作伙伴"], "伙伴科技 · 王经理（伙伴负责人）")
        self.assertEqual(fields["团队覆盖率"], "67%")
        self.assertEqual(fields["团队缺口"], "商务报价")
        self.assertNotIn("标题", fields)

    def test_partner_lead_import_persists_fts_and_marks_bitable_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            init_db(settings)

            preview = import_partner_leads(
                settings,
                dry_run=True,
                http_client_factory=PartnerLeadClient,
                source_verifier=_verified_source,
            )
            result = import_partner_leads(
                settings,
                http_client_factory=PartnerLeadClient,
                source_verifier=_verified_source,
            )
            with connection(settings) as conn:
                notice = conn.execute(
                    "SELECT * FROM notices WHERE id = ?",
                    ("feishu_partner:rec-partner-1",),
                ).fetchone()
                fts_count = conn.execute(
                    "SELECT COUNT(*) FROM notices_fts WHERE notice_id = ?",
                    ("feishu_partner:rec-partner-1",),
                ).fetchone()[0]
            audit_runs = list_feishu_lead_import_runs(settings)

        self.assertEqual(preview.candidate_count, 1)
        self.assertEqual(preview.imported_count, 0)
        self.assertEqual(result.status, "imported")
        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.verified_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(notice["title"], "合作伙伴提交的数据中心服务器采购")
        self.assertEqual(fts_count, 1)
        update = FakeFeishuClient.updated_records[-1][1]
        self.assertEqual(update["状态"], "已入库")
        self.assertEqual(update["公告ID"], "rec-partner-1")
        self.assertEqual(update["项目指纹"], "feishu_partner:rec-partner-1")
        self.assertEqual(update["来源核验"], "已验证")
        self.assertIn("HTTP 200", update["核验摘要"])
        self.assertEqual([item.status for item in audit_runs], ["imported", "preview"])
        self.assertEqual(audit_runs[0].imported_count, 1)
        self.assertEqual(audit_runs[0].verified_count, 1)
        self.assertEqual(audit_runs[1].candidate_count, 1)

    def test_partner_lead_import_rejects_private_network_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            init_db(settings)

            result = import_partner_leads(
                settings,
                dry_run=True,
                http_client_factory=UnsafePartnerLeadClient,
            )

        self.assertEqual(result.candidate_count, 0)
        self.assertEqual(result.unsafe_count, 1)
        self.assertEqual(len(result.invalid_records), 1)
        self.assertIn("不安全", result.invalid_records[0]["reason"])


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DELIVERY_CHANNELS=web,outbox,feishu_bitable\n"
        "TENDERTRACE_FEISHU_APP_ID=cli_test\n"
        "TENDERTRACE_FEISHU_APP_SECRET=secret-feishu\n"
        "TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=base_test\n"
        "TENDERTRACE_FEISHU_BITABLE_TABLE_ID=tbl_test\n"
        "TENDERTRACE_PUBLIC_BASE_URL=https://tt.example.com\n",
        encoding="utf-8",
    )
    return Settings.load(root)


def _verified_source(url: str) -> SourceVerification:
    return SourceVerification(
        status="verified",
        source_url=url,
        final_url=url,
        status_code=200,
        content_type="text/html",
        snapshot_sha256="a" * 64,
        text_excerpt="数据中心服务器采购原文，包含机架服务器、存储和维保服务。",
        selector="main",
        fetched_bytes=2048,
        elapsed_ms=12,
    )


def _notice(notice_id: str, *, cluster_key: str) -> dict:
    return {
        "id": notice_id,
        "source_site": "ccgp",
        "title": f"{notice_id} title",
        "publish_time": "2026-08-06",
        "region": "上海",
        "purchaser": "上海某单位",
        "source_url": f"https://example.com/{notice_id}",
        "attachments": [{"name": "附件", "url": "https://example.com/file.pdf"}],
        "fields": {
            "cluster_key": cluster_key,
            "structured_fields": {
                "project_no": "SH-2026-001",
                "purchaser": "上海某单位",
                "region": "上海",
                "publish_time": "2026-08-06",
                "bid_deadline": "2026-08-20 09:00",
                "budget": "120万元",
            },
            "opportunity_intelligence": {
                "score": 72,
                "level": "B",
                "level_label": "重点观察",
                "stage": "机会确认",
                "scores": {
                    "freshness": 90,
                    "completeness": 82,
                    "credibility": 76,
                    "readiness": 70,
                },
                "project_target": "完成客户需求确认",
                "strategy": "核实预算和技术边界",
                "recommended_actions": [
                    {"role": "机会点负责人", "action": "确认客户关系和投标窗口。"}
                ],
                "risks": ["需补充跨来源佐证"],
                "market_context": {
                    "benchmark": {
                        "message": "高于同品类历史中位数",
                        "sample_count": 8,
                    }
                },
                "competition": {
                    "message": "当前公告披露成交方 上海样例科技有限公司，成交金额 120 万元",
                    "evidence_excerpt": "结果公告原文披露上海样例科技有限公司",
                    "historical_suppliers": [
                        {"name": "上海样例科技有限公司", "count": 2}
                    ],
                },
                "requirement_review": {
                    "coverage_score": 63,
                    "covered_count": 5,
                    "total_count": 8,
                    "missing": ["评分规则", "安全要求"],
                    "recommendations": ["获取评分办法并量化得分空间。"],
                },
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
