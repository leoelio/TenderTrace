from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from tendertrace.config import Settings


class FeishuError(RuntimeError):
    """Raised when Feishu integration is disabled, misconfigured, or rejected."""


@dataclass(frozen=True)
class FeishuStatus:
    enabled: bool
    configured: bool
    base_url: str
    app_id_configured: bool
    app_secret_configured: bool
    default_receive_id_configured: bool
    default_receive_id_type: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FeishuAgentStatus:
    enabled: bool
    configured: bool
    base_url: str
    app_id_configured: bool
    app_secret_configured: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FeishuClient:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.model_request_timeout)

    def get_tenant_access_token(self) -> str:
        self._require_credentials()
        response = self._client.post(
            self._url("/open-apis/auth/v3/tenant_access_token/internal"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            json={
                "app_id": self.settings.feishu_message_app_id(),
                "app_secret": self.settings.feishu_message_app_secret(),
            },
        )
        payload = self._parse_response(response)
        token = str(payload.get("tenant_access_token") or "")
        if not token:
            raise FeishuError("Feishu tenant_access_token is missing in response")
        return token

    def send_text(
        self,
        text: str,
        *,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> dict[str, Any]:
        receive_id = (receive_id or self.settings.feishu_default_receive_id).strip()
        receive_id_type = (receive_id_type or self.settings.feishu_default_receive_id_type).strip()
        if not text.strip():
            raise FeishuError("text is required")
        if not receive_id:
            raise FeishuError("receive_id is required; set FEISHU_DEFAULT_RECEIVE_ID or pass one")
        return self._send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="text",
            content={"text": text},
        )

    def send_card(
        self,
        card: dict[str, Any],
        *,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> dict[str, Any]:
        receive_id = (receive_id or self.settings.feishu_default_receive_id).strip()
        receive_id_type = (receive_id_type or self.settings.feishu_default_receive_id_type).strip()
        if not receive_id:
            raise FeishuError("receive_id is required; set FEISHU_DEFAULT_RECEIVE_ID or pass one")
        if not card:
            raise FeishuError("card is required")
        return self._send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="interactive",
            content=card,
        )

    def reply_text(self, message_id: str, text: str) -> dict[str, Any]:
        if not message_id.strip():
            raise FeishuError("message_id is required")
        if not text.strip():
            raise FeishuError("text is required")
        token = self.get_tenant_access_token()
        response = self._client.post(
            self._url(f"/open-apis/im/v1/messages/{quote(message_id, safe='')}/reply"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        return self._parse_response(response)

    def create_task(
        self,
        *,
        summary: str,
        description: str,
        client_token: str,
        due_timestamp_ms: str = "",
        assignee_open_id: str = "",
    ) -> dict[str, Any]:
        if not summary.strip():
            raise FeishuError("task summary is required")
        token = self.get_tenant_access_token()
        body: dict[str, Any] = {
            "summary": summary[:3000],
            "description": description[:3000],
            "client_token": client_token[:100],
        }
        if due_timestamp_ms:
            body["due"] = {"timestamp": due_timestamp_ms, "is_all_day": False}
            body["reminders"] = [{"relative_fire_minute": 1440}]
        if assignee_open_id:
            body["members"] = [
                {"type": "user", "id": assignee_open_id, "role": "assignee"}
            ]
        response = self._client.post(
            self._url("/open-apis/task/v2/tasks"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"user_id_type": "open_id"},
            json=body,
        )
        return self._parse_response(response)

    def get_task(self, task_guid: str) -> dict[str, Any]:
        if not task_guid.strip():
            raise FeishuError("task_guid is required")
        token = self.get_tenant_access_token()
        response = self._client.get(
            self._url(f"/open-apis/task/v2/tasks/{quote(task_guid, safe='')}"),
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id_type": "open_id"},
        )
        return self._parse_response(response)

    def add_task_members(
        self,
        task_guid: str,
        *,
        assignee_open_ids: list[str],
    ) -> dict[str, Any]:
        if not task_guid.strip():
            raise FeishuError("task_guid is required")
        member_ids = list(
            dict.fromkeys(value.strip() for value in assignee_open_ids if value.strip())
        )
        if not member_ids:
            raise FeishuError("at least one task assignee is required")
        token = self.get_tenant_access_token()
        response = self._client.post(
            self._url(
                f"/open-apis/task/v2/tasks/{quote(task_guid, safe='')}/add_members"
            ),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"user_id_type": "open_id"},
            json={
                "members": [
                    {"type": "user", "id": value, "role": "assignee"}
                    for value in member_ids
                ]
            },
        )
        return self._parse_response(response)

    def list_authorized_users(self, *, limit: int = 100) -> dict[str, Any]:
        safe_limit = min(max(int(limit), 1), 200)
        token = self.get_tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        user_ids: list[str] = []
        department_ids: list[str] = []
        page_token = ""
        while len(user_ids) + len(department_ids) < 1000:
            params: dict[str, object] = {
                "user_id_type": "open_id",
                "department_id_type": "open_department_id",
                "page_size": 100,
            }
            if page_token:
                params["page_token"] = page_token
            payload = self._parse_response(
                self._client.get(
                    self._url("/open-apis/contact/v3/scopes"),
                    headers=headers,
                    params=params,
                )
            )
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            user_ids.extend(str(value) for value in data.get("user_ids") or [] if value)
            department_ids.extend(
                str(value) for value in data.get("department_ids") or [] if value
            )
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                break

        users_by_id: dict[str, dict[str, Any]] = {}
        for department_id in self._authorized_departments(
            department_ids,
            headers=headers,
        ):
            for user in self._department_users(department_id, headers=headers):
                open_id = str(user.get("open_id") or "")
                if open_id:
                    users_by_id[open_id] = user
                if len(users_by_id) >= safe_limit:
                    break
            if len(users_by_id) >= safe_limit:
                break

        unresolved_ids = [
            value
            for value in dict.fromkeys(user_ids)
            if value not in users_by_id
        ][:safe_limit]
        for offset in range(0, len(unresolved_ids), 50):
            chunk = unresolved_ids[offset : offset + 50]
            params: list[tuple[str, str]] = [
                ("user_ids", value) for value in chunk
            ] + [
                ("user_id_type", "open_id"),
                ("department_id_type", "open_department_id"),
            ]
            payload = self._parse_response(
                self._client.get(
                    self._url("/open-apis/contact/v3/users/batch"),
                    headers=headers,
                    params=params,
                )
            )
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            for user in data.get("items") or []:
                if not isinstance(user, dict):
                    continue
                open_id = str(user.get("open_id") or "")
                if open_id:
                    users_by_id[open_id] = user

        items = [
            self._directory_user(user)
            for user in users_by_id.values()
            if self._active_user(user)
        ]
        items.sort(key=lambda item: (str(item["name"]).casefold(), str(item["open_id"])))
        return {
            "status": "ready",
            "items": items[:safe_limit],
            "authorized_user_count": len(set(user_ids)),
            "authorized_department_count": len(set(department_ids)),
            "returned_count": min(len(items), safe_limit),
        }

    def create_calendar_event(
        self,
        *,
        calendar_id: str,
        summary: str,
        description: str,
        start_timestamp: str,
        end_timestamp: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not calendar_id.strip():
            raise FeishuError("calendar_id is required")
        token = self.get_tenant_access_token()
        response = self._client.post(
            self._url(
                f"/open-apis/calendar/v4/calendars/{quote(calendar_id, safe='')}/events"
            ),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"idempotency_key": idempotency_key, "user_id_type": "open_id"},
            json={
                "summary": summary[:1000],
                "description": description[:40960],
                "need_notification": True,
                "start_time": {
                    "timestamp": start_timestamp,
                    "timezone": self.settings.timezone,
                },
                "end_time": {
                    "timestamp": end_timestamp,
                    "timezone": self.settings.timezone,
                },
                "visibility": "public",
            },
        )
        return self._parse_response(response)

    def upload_file(self, path: Path | str) -> str:
        file_path = Path(path)
        if not file_path.is_file():
            raise FeishuError("report file does not exist")
        size = file_path.stat().st_size
        if size <= 0:
            raise FeishuError("report file is empty")
        if size > 30 * 1024 * 1024:
            raise FeishuError("report file exceeds Feishu's 30 MB limit")
        token = self.get_tenant_access_token()
        with file_path.open("rb") as file_handle:
            response = self._client.post(
                self._url("/open-apis/im/v1/files"),
                headers={"Authorization": f"Bearer {token}"},
                data={"file_type": "stream", "file_name": file_path.name},
                files={
                    "file": (
                        file_path.name,
                        file_handle,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
        payload = self._parse_response(response)
        data = payload.get("data")
        file_key = str(data.get("file_key") or "") if isinstance(data, dict) else ""
        if not file_key:
            raise FeishuError("Feishu file_key is missing in response")
        return file_key

    def send_file(
        self,
        path: Path | str,
        *,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> dict[str, Any]:
        receive_id = (receive_id or self.settings.feishu_default_receive_id).strip()
        receive_id_type = (receive_id_type or self.settings.feishu_default_receive_id_type).strip()
        if not receive_id:
            raise FeishuError("receive_id is required; set FEISHU_DEFAULT_RECEIVE_ID or pass one")
        file_key = self.upload_file(path)
        return self._send_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            msg_type="file",
            content={"file_key": file_key},
        )

    def _send_message(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        msg_type: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        response = self._client.post(
            self._url("/open-apis/im/v1/messages"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
        )
        return self._parse_response(response)

    def list_chats(self, *, page_size: int = 20, page_token: str | None = None) -> dict[str, Any]:
        token = self.get_tenant_access_token()
        params: dict[str, object] = {"page_size": min(max(page_size, 1), 100)}
        if page_token:
            params["page_token"] = page_token
        response = self._client.get(
            self._url("/open-apis/im/v1/chats"),
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        payload = self._parse_response(response)
        data = payload.get("data")
        return data if isinstance(data, dict) else {"items": []}

    def _authorized_departments(
        self,
        department_ids: list[str],
        *,
        headers: dict[str, str],
    ) -> list[str]:
        resolved = list(dict.fromkeys(department_ids))
        for root_id in list(resolved):
            page_token = ""
            while True:
                params: dict[str, object] = {
                    "department_id_type": "open_department_id",
                    "user_id_type": "open_id",
                    "fetch_child": True,
                    "page_size": 100,
                }
                if page_token:
                    params["page_token"] = page_token
                payload = self._parse_response(
                    self._client.get(
                        self._url(
                            "/open-apis/contact/v3/departments/"
                            f"{quote(root_id, safe='')}/children"
                        ),
                        headers=headers,
                        params=params,
                    )
                )
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                for item in data.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    department_id = str(
                        item.get("open_department_id") or item.get("department_id") or ""
                    )
                    if department_id and department_id not in resolved:
                        resolved.append(department_id)
                if not data.get("has_more"):
                    break
                page_token = str(data.get("page_token") or "")
                if not page_token:
                    break
        return resolved[:1000]

    def _department_users(
        self,
        department_id: str,
        *,
        headers: dict[str, str],
    ) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, object] = {
                "department_id": department_id,
                "department_id_type": "open_department_id",
                "user_id_type": "open_id",
                "page_size": 100,
            }
            if page_token:
                params["page_token"] = page_token
            payload = self._parse_response(
                self._client.get(
                    self._url("/open-apis/contact/v3/users/find_by_department"),
                    headers=headers,
                    params=params,
                )
            )
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            users.extend(item for item in data.get("items") or [] if isinstance(item, dict))
            if not data.get("has_more"):
                return users
            page_token = str(data.get("page_token") or "")
            if not page_token:
                return users

    @staticmethod
    def _active_user(user: dict[str, Any]) -> bool:
        status = user.get("status") if isinstance(user.get("status"), dict) else {}
        return not bool(status.get("is_resigned")) and status.get("is_activated") is not False

    @staticmethod
    def _directory_user(user: dict[str, Any]) -> dict[str, Any]:
        avatar = user.get("avatar") if isinstance(user.get("avatar"), dict) else {}
        return {
            "open_id": str(user.get("open_id") or ""),
            "name": str(user.get("name") or user.get("en_name") or "未命名成员"),
            "department_ids": [str(value) for value in user.get("department_ids") or []],
            "avatar_url": str(avatar.get("avatar_72") or ""),
        }

    def _require_credentials(self) -> None:
        if not self.settings.feishu_enabled:
            raise FeishuError("Feishu integration is disabled; set FEISHU_ENABLED=true")
        if (
            not self.settings.feishu_message_app_id_present
            or not self.settings.feishu_message_app_secret_present
        ):
            raise FeishuError("FEISHU_APP_ID and FEISHU_APP_SECRET are required")

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as http_exc:
                raise FeishuError(f"Feishu HTTP {response.status_code}") from http_exc
            raise FeishuError("Feishu response is not JSON") from exc
        if not isinstance(payload, dict):
            raise FeishuError("Feishu response JSON must be an object")
        code = payload.get("code", 0)
        if code != 0:
            messages = {
                232034: "应用在当前租户不可用或未启用，请先发布应用并确认租户已安装",
            }
            message = messages.get(code, str(payload.get("msg") or "unknown error"))
            raise FeishuError(f"Feishu API error {code}: {message}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FeishuError(f"Feishu HTTP {response.status_code}") from exc
        return payload

    def _url(self, path: str) -> str:
        return f"{self.settings.feishu_base_url}{path}"


def feishu_status(settings: Settings) -> FeishuStatus:
    return FeishuStatus(
        enabled=settings.feishu_enabled,
        configured=(
            settings.feishu_enabled
            and settings.feishu_message_app_id_present
            and settings.feishu_message_app_secret_present
        ),
        base_url=settings.feishu_base_url,
        app_id_configured=settings.feishu_message_app_id_present,
        app_secret_configured=settings.feishu_message_app_secret_present,
        default_receive_id_configured=bool(settings.feishu_default_receive_id.strip()),
        default_receive_id_type=settings.feishu_default_receive_id_type,
    )


def feishu_agent_status(settings: Settings) -> FeishuAgentStatus:
    return FeishuAgentStatus(
        enabled=settings.feishu_agent_enabled,
        configured=(
            settings.feishu_agent_enabled
            and settings.feishu_agent_app_id_present
            and settings.feishu_agent_app_secret_present
        ),
        base_url=settings.feishu_agent_base_url,
        app_id_configured=settings.feishu_agent_app_id_present,
        app_secret_configured=settings.feishu_agent_app_secret_present,
    )
