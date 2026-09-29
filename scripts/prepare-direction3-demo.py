from __future__ import annotations

import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tendertrace.config import Settings  # noqa: E402
from tendertrace.db import connection, init_db, json_dumps  # noqa: E402
from tendertrace.notice_change_reviews import register_notice_change_review  # noqa: E402
from tendertrace.notice_changes import record_notice_revision  # noqa: E402
from tendertrace.opportunity_requirements import upsert_requirement  # noqa: E402


NOTICE_ID = "ccgp:direction3-hainan-monitor-correction"
SOURCE_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202508/t20250812_25149498.htm"


def main() -> None:
    settings = Settings.load(ROOT)
    init_db(settings)
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, publish_time,
                region, purchaser, content_text, core_content, attachments_json,
                fields_json, snapshot_sha256, simhash64, notice_type, notice_type_label
            ) VALUES (?, 'ccgp', ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, '', 'tender', '招标公告')
            ON CONFLICT(id) DO NOTHING
            """,
            (
                NOTICE_ID,
                SOURCE_URL,
                SOURCE_URL,
                "海南省农垦加来高级中学校园监控采购项目（二次）",
                "2025-07-24 00:00:00",
                "海南省临高县",
                "海南省农垦加来高级中学",
                _before_content(),
                "视频综合平台技术参数与投标截止时间，其他资格条件保持不变。",
                json_dumps({
                    "project_no": "[HNBS001]20250500001[GK]-1",
                    "budget": "以采购文件为准",
                    "bid_deadline": "2025-08-14 08:30:00",
                    "structured_fields": {
                        "project_no": "[HNBS001]20250500001[GK]-1",
                        "budget": "以采购文件为准",
                        "bid_deadline": "2025-08-14 08:30:00",
                    },
                    "demo_case": "direction3_real_correction",
                }),
                hashlib.sha256(_before_content().encode("utf-8")).hexdigest(),
            ),
        )
        conn.execute(
            """
            INSERT INTO opportunity_workflows(
                notice_id, stage, owner_open_id, owner_name, next_action, due_at,
                qualification_score, qualification_status, decision, decision_reason,
                decision_by, decision_at, updated_by
            ) VALUES (?, 'bidding', '', '投标经理', '等待公告变更扫描', ?,
                      86, 'passed', 'go', '原版本技术与时限满足投标条件',
                      '投标经理', '2025-08-01T10:00:00+08:00', 'demo:direction3')
            ON CONFLICT(notice_id) DO NOTHING
            """,
            (NOTICE_ID, "2025-08-13T18:00:00+08:00"),
        )
        members = (
            ("member-bid", "投标经理", "bid_manager", "统筹变更复核与投标决策"),
            ("member-tech", "技术负责人", "solution", "核对视频综合平台参数与产品证据"),
            ("member-legal", "合规负责人", "legal", "确认资格条件未受本次更正影响"),
        )
        for member_key, name, role, responsibility in members:
            member_id = _id("member", member_key)
            conn.execute(
                """
                INSERT OR IGNORE INTO opportunity_team_members(
                    id, notice_id, member_key, member_name, role, responsibility,
                    status, feishu_sync_status, added_by
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', 'pending', 'demo:direction3')
                """,
                (member_id, NOTICE_ID, member_key, name, role, responsibility),
            )

    upsert_requirement(
        settings,
        notice_id=NOTICE_ID,
        requirement_key="DEADLINE-01",
        requirement_type="deadline",
        title="投标文件提交截止时间",
        evidence_text="原提交投标文件截止时间为2025年08月14日08时30分。",
        source_url=SOURCE_URL,
        source_locator="更正公告/二、更正信息/第3项",
        mandatory=True,
        confidence=100,
        status="confirmed",
        assignee_member_id=_id("member", "member-bid"),
        due_at="2025-08-13T18:00:00+08:00",
        actor="demo:direction3",
    )
    technical_output = upsert_requirement(
        settings,
        notice_id=NOTICE_ID,
        requirement_key="TECH-HDMI-OUTPUT",
        requirement_type="technical",
        title="视频综合平台 4K HDMI 输出板卡端口数",
        evidence_text="原技术参数：≥6 6口4K HDMI输出板（原网页文本保留）。",
        source_url=SOURCE_URL,
        source_locator="更正公告/二、更正信息/第1项",
        mandatory=True,
        confidence=100,
        status="confirmed",
        assignee_member_id=_id("member", "member-tech"),
        actor="demo:direction3",
    )
    technical_input = upsert_requirement(
        settings,
        notice_id=NOTICE_ID,
        requirement_key="TECH-HDMI-INPUT",
        requirement_type="technical",
        title="视频综合平台 1080P HDMI 输入板卡端口数",
        evidence_text="原技术参数：≥44口1080P HDMI输入板。",
        source_url=SOURCE_URL,
        source_locator="更正公告/二、更正信息/第2项",
        mandatory=True,
        confidence=100,
        status="confirmed",
        assignee_member_id=_id("member", "member-tech"),
        actor="demo:direction3",
    )
    upsert_requirement(
        settings,
        notice_id=NOTICE_ID,
        requirement_key="QUAL-UNCHANGED",
        requirement_type="qualification",
        title="供应商基本资格与联合体限制",
        evidence_text="其他内容不变；本项目不接受联合体投标。",
        source_url=SOURCE_URL,
        source_locator="更正公告/三、其他补充事项/第7项",
        mandatory=True,
        confidence=96,
        status="confirmed",
        assignee_member_id=_id("member", "member-legal"),
        actor="demo:direction3",
    )
    with connection(settings) as conn:
        capability_id = _id("capability", "video-platform-hdmi")
        conn.execute(
            """
            INSERT OR IGNORE INTO enterprise_capabilities(
                id, capability_key, title, capability_type, evidence_text,
                source_url, source_locator, verification_status, owner, created_by
            ) VALUES (?, 'VIDEO-HDMI-01', '视频综合平台 HDMI 板卡适配能力', 'product',
                      '企业产品配置表与检测报告支持 HDMI 板卡配置。', ?,
                      '企业产品证据库/视频综合平台/板卡配置', 'verified', '技术负责人', 'demo:direction3')
            """,
            (capability_id, SOURCE_URL),
        )
        for requirement in (technical_output, technical_input):
            conn.execute(
                """
                INSERT OR IGNORE INTO requirement_capability_matches(
                    id, notice_id, requirement_id, capability_id, verdict,
                    confidence, rationale, status, decided_by, decision_note, decided_at
                ) VALUES (?, ?, ?, ?, 'match', 92, '原版本参数已匹配企业能力证据',
                          'accepted', '技术负责人', '已按原版本确认', '2025-08-01T11:00:00+08:00')
                """,
                (_id("match", requirement.id), NOTICE_ID, requirement.id, capability_id),
            )
        existing = conn.execute(
            "SELECT id FROM notice_revisions WHERE notice_id = ? LIMIT 1", (NOTICE_ID,)
        ).fetchone()
        if existing is None:
            revision = record_notice_revision(
                conn,
                notice_id=NOTICE_ID,
                before={
                    "bid_deadline": "2025-08-14 08:30:00",
                    "content_text": _before_content(),
                    "core_content": "视频综合平台技术参数与原投标截止时间。",
                },
                after={
                    "bid_deadline": "2025-08-28 09:30:00",
                    "content_text": _after_content(),
                    "core_content": "视频综合平台输出板更正为≥6口、输入板更正为≥4口；投标截止顺延至2025年08月28日09时30分。",
                },
            )
            assert revision is not None
            register_notice_change_review(
                conn,
                revision,
                review_sla_hours=settings.change_review_sla_hours,
            )
            conn.execute(
                """
                UPDATE notices
                SET publish_time = '2025-08-12 17:41:00', content_text = ?, core_content = ?,
                    fields_json = ?, snapshot_sha256 = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    _after_content(),
                    "视频综合平台输出板更正为≥6口、输入板更正为≥4口；投标截止顺延至2025年08月28日09时30分。",
                    json_dumps({
                        "project_no": "[HNBS001]20250500001[GK]-1",
                        "budget": "以采购文件为准",
                        "bid_deadline": "2025-08-28 09:30:00",
                        "structured_fields": {
                            "project_no": "[HNBS001]20250500001[GK]-1",
                            "budget": "以采购文件为准",
                            "bid_deadline": "2025-08-28 09:30:00",
                        },
                        "demo_case": "direction3_real_correction",
                    }),
                    hashlib.sha256(_after_content().encode("utf-8")).hexdigest(),
                    NOTICE_ID,
                ),
            )
    print(NOTICE_ID)


def _before_content() -> str:
    return (
        "原采购需求：视频综合平台技术参数中≥6 6口4K HDMI输出板；"
        "≥44口1080P HDMI输入板。原提交投标文件截止时间为2025年08月14日08时30分。"
    )


def _after_content() -> str:
    return (
        "更正为：≥6口4K HDMI输出板；≥4口1080P HDMI输入板。"
        "提交投标文件截止时间更正为2025年08月28日09时30分。其他内容不变。"
    )


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


if __name__ == "__main__":
    main()
