from pathlib import Path
import tempfile
import unittest

from tendertrace.change_impact_engine import (
    confirm_change_impact_action,
    dispatch_change_impact,
    get_change_impact,
)
from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.integrations.feishu import FeishuError
from tendertrace.notice_changes import record_notice_revision
from tendertrace.opportunity_requirements import upsert_requirement


class _FeishuClient:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls = 0
        self.tokens: list[str] = []

    def _fail(self) -> None:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise FeishuError("temporary failure")

    def send_card(self, card, *, receive_id: str, receive_id_type: str):
        self._fail()
        return {"data": {"message_id": "om_change"}}

    def create_task(self, *, client_token: str, **kwargs):
        self._fail()
        self.tokens.append(client_token)
        return {"data": {"task": {"guid": f"task-{len(self.tokens)}"}}}

    def create_calendar_event(self, *, idempotency_key: str, **kwargs):
        self._fail()
        self.tokens.append(idempotency_key)
        return {"data": {"event": {"event_id": "event-change"}}}


class ChangeImpactEngineTests(unittest.TestCase):
    def test_structured_events_target_only_affected_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            _revision(settings, deadline="2025-08-28 09:30:00", output_ports="6")

            payload = get_change_impact(settings, "ccgp:real-correction")

        current = payload["current_round"]
        self.assertEqual(set(current["change_types"]), {"deadline", "technical"})
        requirement_items = [item for item in current["items"] if item["target_type"] == "requirement"]
        affected_titles = {
            item["target_title"] for item in requirement_items
            if item["impact_status"] != "unaffected"
        }
        unaffected_titles = {
            item["target_title"] for item in requirement_items
            if item["impact_status"] == "unaffected"
        }
        self.assertEqual(affected_titles, {"投标截止时间", "视频综合平台输出板卡"})
        self.assertIn("营业执照有效", unaffected_titles)
        self.assertTrue(all(item["revision_id"] == current["revision_id"] for item in current["items"]))
        self.assertTrue(any(action["action_type"] == "update_calendar" for action in current["actions"]))

    def test_consecutive_revisions_create_separate_rounds_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            _revision(settings, deadline="2025-08-28 09:30:00", output_ports="6")
            first = get_change_impact(settings, "ccgp:real-correction")
            first_ids = {action["id"] for action in first["current_round"]["actions"]}
            get_change_impact(settings, "ccgp:real-correction")
            _revision(settings, deadline="2025-08-29 09:30:00", output_ports="8")
            second = get_change_impact(settings, "ccgp:real-correction")

        self.assertEqual(second["round_count"], 2)
        self.assertEqual({round_item["round_number"] for round_item in second["rounds"]}, {1, 2})
        second_ids = {action["id"] for action in second["current_round"]["actions"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertEqual(len(second_ids), len(second["current_round"]["actions"]))

    def test_confirmation_failure_and_retry_preserve_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _seed(settings)
            _revision(settings, deadline="2025-08-28 09:30:00", output_ports="6")
            payload = get_change_impact(settings, "ccgp:real-correction")
            round_id = payload["current_round"]["id"]
            action = next(
                item for item in payload["current_round"]["actions"]
                if item["action_type"] == "update_calendar"
            )
            confirm_change_impact_action(
                settings,
                "ccgp:real-correction",
                action["id"],
                actor="投标经理",
                note="已核对新截止时间",
            )
            client = _FeishuClient(fail_first=True)
            failed = dispatch_change_impact(
                settings, "ccgp:real-correction", round_id, actor="投标经理", client=client
            )
            retried = dispatch_change_impact(
                settings, "ccgp:real-correction", round_id, actor="投标经理", client=client
            )
            final = get_change_impact(settings, "ccgp:real-correction")
            current_action = next(item for item in final["current_round"]["actions"] if item["id"] == action["id"])

        self.assertEqual(failed["status"], "partial")
        self.assertEqual(retried["status"], "sent")
        self.assertEqual(current_action["message_status"], "sent")
        self.assertEqual(current_action["task_status"], "sent")
        self.assertEqual(current_action["calendar_status"], "sent")
        self.assertGreaterEqual(current_action["retry_count"], 1)
        self.assertEqual(len(set(client.tokens)), len(client.tokens))


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nFEISHU_CALENDAR_ID=calendar-test\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _seed(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(
                id, source_site, source_url, canonical_url, title, content_text, core_content, fields_json
            ) VALUES (?, 'ccgp', ?, ?, ?, ?, ?, ?)
            """,
            (
                "ccgp:real-correction",
                "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202508/t20250812_25149498.htm",
                "https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202508/t20250812_25149498.htm",
                "海南省农垦加来高级中学校园监控采购项目（二次）",
                "视频综合平台≥66路4K HDMI输出，投标截止2025-08-14 08:30:00。",
                "视频综合平台≥66路4K HDMI输出。",
                '{"structured_fields":{"bid_deadline":"2025-08-14 08:30:00"}}',
            ),
        )
        conn.execute(
            """
            INSERT INTO opportunity_workflows(
                notice_id, stage, owner_open_id, owner_name, decision, qualification_status
            ) VALUES (?, 'bidding', 'ou_owner', '投标经理', 'go', 'passed')
            """,
            ("ccgp:real-correction",),
        )
    for key, requirement_type, title in (
        ("DEADLINE-01", "deadline", "投标截止时间"),
        ("TECH-OUTPUT", "technical", "视频综合平台输出板卡"),
        ("QUAL-01", "qualification", "营业执照有效"),
    ):
        upsert_requirement(
            settings,
            notice_id="ccgp:real-correction",
            requirement_key=key,
            requirement_type=requirement_type,
            title=title,
            evidence_text="可核验的采购公告原文。",
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202508/t20250812_25149498.htm",
            source_locator=f"采购需求/{title}",
            status="confirmed",
        )


def _revision(settings: Settings, *, deadline: str, output_ports: str) -> None:
    with connection(settings) as conn:
        latest = conn.execute(
            "SELECT after_json FROM notice_revisions WHERE notice_id = ? ORDER BY rowid DESC LIMIT 1",
            ("ccgp:real-correction",),
        ).fetchone()
        before = (
            __import__("json").loads(str(latest["after_json"]))
            if latest else {
                "bid_deadline": "2025-08-14 08:30:00",
                "content_text": "视频综合平台≥66路4K HDMI输出。",
            }
        )
        after = {
            "bid_deadline": deadline,
            "content_text": f"视频综合平台≥{output_ports}路4K HDMI输出。",
        }
        record_notice_revision(
            conn,
            notice_id="ccgp:real-correction",
            before=before,
            after=after,
        )


if __name__ == "__main__":
    unittest.main()
