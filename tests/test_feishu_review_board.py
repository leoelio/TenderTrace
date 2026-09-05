from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tendertrace.config import Settings
from tendertrace.db import connection, init_db
from tendertrace.delivery.preferences import save_feishu_receiver
from tendertrace.integrations.feishu_review_board import send_requirement_review_digest
from tendertrace.opportunity_requirements import upsert_requirement
from tendertrace.requirement_review_board import sync_requirement_review_cases


class _FakeFeishuClient:
    def __init__(self) -> None:
        self.cards: list[dict[str, object]] = []
        self.receivers: list[tuple[str, str]] = []

    def send_card(self, card, **kwargs):
        self.cards.append(card)
        self.receivers.append(
            (str(kwargs.get("receive_id") or ""), str(kwargs.get("receive_id_type") or ""))
        )
        return {"data": {"message_id": f"review-{len(self.cards)}"}}


class FeishuReviewBoardTests(unittest.TestCase):
    def test_review_digest_is_evidence_based_and_deduplicated_per_group_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _settings(Path(tmp))
            _insert_notice(settings)
            upsert_requirement(
                settings,
                notice_id="notice-1",
                requirement_key="QUAL-01",
                requirement_type="qualification",
                title="营业执照有效",
                evidence_text="投标人须具有有效的营业执照。",
                source_url="https://example.com/notice-1",
                source_locator="招标文件第 3 页",
                mandatory=True,
                confidence=60,
            )
            sync_requirement_review_cases(settings, "notice-1")
            save_feishu_receiver(
                settings,
                receive_id="oc_review_team",
                receive_id_type="chat_id",
                label="会审群",
            )
            client = _FakeFeishuClient()
            def suggestions(*_args):
                return [
                    {
                        "requirement_key": "QUAL-01",
                        "suggestion_label": "建议升级",
                        "consensus": "split",
                        "opinion_count": 4,
                    }
                ]
            first = send_requirement_review_digest(
                settings,
                "notice-1",
                client=client,
                suggestion_loader=suggestions,
            )
            duplicate = send_requirement_review_digest(
                settings,
                "notice-1",
                client=client,
                suggestion_loader=suggestions,
            )

        self.assertEqual(first.status, "sent")
        self.assertEqual(first.message_id, "review-1")
        self.assertEqual(duplicate.status, "skipped")
        self.assertEqual(client.receivers, [("oc_review_team", "chat_id")])
        card_text = str(client.cards[0])
        self.assertIn("服务器采购项目", card_text)
        self.assertIn("QUAL-01", card_text)
        self.assertIn("建议升级", card_text)
        self.assertIn("项目意见 notice-1", card_text)
        self.assertIn("opportunity=notice-1", card_text)


def _settings(root: Path) -> Settings:
    (root / ".env.local").write_text(
        "TENDERTRACE_DB_PATH=data/test.sqlite3\nTENDERTRACE_SCHEDULER_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings.load(root)
    init_db(settings)
    return settings


def _insert_notice(settings: Settings) -> None:
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO notices(id, source_site, source_url, canonical_url, title)
            VALUES ('notice-1', 'ccgp', 'https://example.com/notice-1',
                    'https://example.com/notice-1', '服务器采购项目')
            """
        )


if __name__ == "__main__":
    unittest.main()
