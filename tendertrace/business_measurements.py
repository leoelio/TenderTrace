from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from statistics import mean
from typing import Any

from tendertrace.config import Settings
from tendertrace.db import connection, init_db


TASK_TYPE_LABELS = {
    "opportunity_verification": "机会核验",
    "capability_matching": "能力匹配",
    "change_review": "公告变更复核",
    "group_handoff": "群内协作交接",
}
QUALITY_STATUS_LABELS = {
    "not_reviewed": "待质量复核",
    "passed": "质量复核通过",
    "failed": "质量复核未通过",
}


@dataclass(frozen=True)
class BusinessMeasurement:
    id: str
    task_type: str
    task_type_label: str
    sample_ref: str
    baseline_minutes: float
    assisted_minutes: float
    quality_status: str
    quality_status_label: str
    reviewer: str
    note: str
    recorded_by: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def upsert_business_measurement(
    settings: Settings,
    *,
    task_type: str,
    sample_ref: str,
    baseline_minutes: float,
    assisted_minutes: float,
    quality_status: str,
    reviewer: str,
    note: str,
    recorded_by: str,
) -> BusinessMeasurement:
    init_db(settings)
    values = {
        "task_type": task_type.strip(),
        "sample_ref": sample_ref.strip(),
        "quality_status": quality_status.strip(),
        "reviewer": reviewer.strip(),
        "note": note.strip(),
        "recorded_by": recorded_by.strip(),
    }
    baseline = _minutes(baseline_minutes, "baseline_minutes")
    assisted = _minutes(assisted_minutes, "assisted_minutes")
    if not values["sample_ref"]:
        raise ValueError("sample_ref is required")
    if values["task_type"] not in TASK_TYPE_LABELS:
        raise ValueError(f"unsupported task_type: {values['task_type']}")
    if values["quality_status"] not in QUALITY_STATUS_LABELS:
        raise ValueError(f"unsupported quality_status: {values['quality_status']}")
    if values["quality_status"] != "not_reviewed" and not values["reviewer"]:
        raise ValueError("reviewer is required after quality review")
    if not values["recorded_by"]:
        raise ValueError("recorded_by is required")
    measurement_id = _measurement_id(values["task_type"], values["sample_ref"])
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO business_measurements(
                id, task_type, sample_ref, baseline_minutes, assisted_minutes,
                quality_status, reviewer, note, recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_type, sample_ref) DO UPDATE SET
                baseline_minutes = excluded.baseline_minutes,
                assisted_minutes = excluded.assisted_minutes,
                quality_status = excluded.quality_status,
                reviewer = excluded.reviewer,
                note = excluded.note,
                recorded_by = excluded.recorded_by
            """,
            (
                measurement_id,
                values["task_type"],
                values["sample_ref"],
                baseline,
                assisted,
                values["quality_status"],
                values["reviewer"],
                values["note"],
                values["recorded_by"],
            ),
        )
        row = conn.execute("SELECT * FROM business_measurements WHERE id = ?", (measurement_id,)).fetchone()
    assert row is not None
    return _from_row(row)


def list_business_measurements(settings: Settings, *, limit: int = 100) -> list[BusinessMeasurement]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT * FROM business_measurements
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (min(max(int(limit), 1), 500),),
        ).fetchall()
    return [_from_row(row) for row in rows]


def business_measurement_summary(settings: Settings) -> dict[str, object]:
    items = list_business_measurements(settings)
    passed = [item for item in items if item.quality_status == "passed"]
    baseline_total = round(sum(item.baseline_minutes for item in passed), 2)
    assisted_total = round(sum(item.assisted_minutes for item in passed), 2)
    saved_total = round(max(0.0, baseline_total - assisted_total), 2)
    return {
        "status": "measured" if passed else "not_measured",
        "record_count": len(items),
        "quality_reviewed_count": sum(item.quality_status != "not_reviewed" for item in items),
        "quality_passed_count": len(passed),
        "quality_failed_count": sum(item.quality_status == "failed" for item in items),
        "baseline_minutes": baseline_total,
        "assisted_minutes": assisted_total,
        "saved_minutes": saved_total,
        "time_saving_rate": _ratio(saved_total, baseline_total),
        "average_saved_minutes": round(mean(item.baseline_minutes - item.assisted_minutes for item in passed), 2)
        if passed
        else 0.0,
        "by_task_type": {
            task_type: _task_summary([item for item in passed if item.task_type == task_type])
            for task_type in TASK_TYPE_LABELS
        },
        "items": [item.to_dict() for item in items],
        "note": (
            "仅汇总质量复核通过的实测任务；未复核或未通过样本不计入节省时间。"
            if passed
            else "暂无质量复核通过的实测任务，不能估算业务节省。"
        ),
    }


def _task_summary(items: list[BusinessMeasurement]) -> dict[str, object]:
    baseline = sum(item.baseline_minutes for item in items)
    assisted = sum(item.assisted_minutes for item in items)
    saved = max(0.0, baseline - assisted)
    return {
        "count": len(items),
        "baseline_minutes": round(baseline, 2),
        "assisted_minutes": round(assisted, 2),
        "saved_minutes": round(saved, 2),
        "time_saving_rate": _ratio(saved, baseline),
    }


def _minutes(value: object, field: str) -> float:
    try:
        minutes = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not 0 < minutes <= 24 * 60:
        raise ValueError(f"{field} must be greater than 0 and no more than 1440")
    return minutes


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 3) if denominator > 0 else 0.0


def _measurement_id(task_type: str, sample_ref: str) -> str:
    return hashlib.sha256(f"{task_type}|{sample_ref}".encode()).hexdigest()[:24]


def _from_row(row: Any) -> BusinessMeasurement:
    task_type = str(row["task_type"] or "")
    quality_status = str(row["quality_status"] or "not_reviewed")
    return BusinessMeasurement(
        id=str(row["id"]),
        task_type=task_type,
        task_type_label=TASK_TYPE_LABELS.get(task_type, task_type),
        sample_ref=str(row["sample_ref"] or ""),
        baseline_minutes=float(row["baseline_minutes"] or 0),
        assisted_minutes=float(row["assisted_minutes"] or 0),
        quality_status=quality_status,
        quality_status_label=QUALITY_STATUS_LABELS.get(quality_status, quality_status),
        reviewer=str(row["reviewer"] or ""),
        note=str(row["note"] or ""),
        recorded_by=str(row["recorded_by"] or ""),
        created_at=str(row["created_at"] or ""),
    )
