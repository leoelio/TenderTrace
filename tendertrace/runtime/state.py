from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class RunState:
    run_id: str
    original_query: str
    status: str = "created"
    current_node: str | None = None
    repair_rounds: int = 0
    intent: dict[str, Any] = field(default_factory=dict)
    source_plan: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    notices: list[dict[str, Any]] = field(default_factory=list)
    clusters: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    funnel: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def new(cls, original_query: str, run_id: str | None = None) -> "RunState":
        return cls(run_id=run_id or str(uuid4()), original_query=original_query)

    def with_updates(self, **changes: Any) -> "RunState":
        return replace(self, updated_at=utc_now_iso(), **changes)

    def append_error(self, *, node: str | None, message: str) -> "RunState":
        errors = [*self.errors, {"node": node, "message": message, "at": utc_now_iso()}]
        return self.with_updates(errors=errors, status="failed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RunState":
        return cls(**value)

