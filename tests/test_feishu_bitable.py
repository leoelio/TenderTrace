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
)


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
                                "fields": {"项目指纹": "ccgp:existing"},
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
        created = FakeFeishuClient.created_records[0]["fields"]
        self.assertEqual(created["标题"], "new title")
        self.assertEqual(created["关键词"], "服务器")
        self.assertEqual(created["状态"], "新增")
        self.assertEqual(created["项目指纹"], "ccgp:new")
        self.assertIn("/api/outbox/report.docx", created["Word 报告"])
        updated = FakeFeishuClient.updated_records[0][1]
        self.assertEqual(sorted(updated), ["Word 报告", "最近同步时间", "运行ID"])


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
        },
    }


if __name__ == "__main__":
    unittest.main()
