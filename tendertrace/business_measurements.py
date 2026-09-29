from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from statistics import median
from typing import Any
from uuid import uuid4

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps


TASK_TYPE_LABELS = {
    "opportunity_discovery": "机会发现",
    "opportunity_verification": "机会核验",
    "requirement_breakdown": "招标要求拆解",
    "capability_matching": "能力匹配",
    "change_review": "公告变更复核",
    "expert_review": "多角色会审",
    "decision_review": "投标决策复核",
    "group_handoff": "群内协作交接",
    "material_reuse": "历史材料复用",
    "source_verification": "跨来源核验",
    "live_challenge": "现场检索挑战",
    "replay_reliability": "演示回放校验",
    "user_experience": "统一交互体验",
    "partner_due_diligence": "合作方尽调",
    "external_event_response": "外部事件响应",
    "scenario_training": "情景训练演练",
}
QUALITY_STATUS_LABELS = {
    "not_reviewed": "待质量复核",
    "passed": "质量复核通过",
    "failed": "质量复核未通过",
}
SEQUENCE_LABELS = {
    "manual_first": "先人工后辅助",
    "assisted_first": "先辅助后人工",
    "randomized": "随机交叉顺序",
}
MIN_GENERALIZATION_SAMPLE = 5

DIRECTION_COVERAGE = (
    (1, "投标数字孪生", "opportunity_verification"),
    (2, "可审计证据链与证据显微镜", "opportunity_verification"),
    (3, "变更影响引擎与公告冲击波", "change_review"),
    (4, "智能拆标与履约作战图", "requirement_breakdown"),
    (5, "企业能力护照与匹配矩阵", "capability_matching"),
    (6, "可质询多智能体会审", "expert_review"),
    (7, "可解释投标决策沙盘", "decision_review"),
    (8, "一键飞书投标战情室", "group_handoff"),
    (9, "企业投标记忆体", "material_reuse"),
    (10, "全国与全球机会雷达", "opportunity_discovery"),
    (11, "跨来源可信关系图", "source_verification"),
    (12, "可复算业务价值实验室", "value_lab"),
    (13, "评委现场挑战模式", "live_challenge"),
    (14, "演示可靠性与真实回放控制台", "replay_reliability"),
    (15, "统一视觉、状态语言与业务动效", "user_experience"),
    (16, "合作方全景尽调与风险雷达", "partner_due_diligence"),
    (17, "实时商机战情图与外部事件影响引擎", "external_event_response"),
    (18, "情景训练与智能问答演练中心", "scenario_training"),
)


@dataclass(frozen=True)
class BusinessMeasurement:
    id: str
    task_type: str
    task_type_label: str
    sample_ref: str
    experiment_id: str
    experiment_version: int
    participant: str
    document_type: str
    file_count: int
    sequence_order: str
    sequence_order_label: str
    conditions: str
    source_url: str
    raw_record_url: str
    gold_standard_url: str
    baseline_minutes: float
    assisted_minutes: float
    baseline_active_minutes: float
    assisted_active_minutes: float
    baseline_machine_wait_seconds: float
    assisted_machine_wait_seconds: float
    baseline_omissions: int
    assisted_omissions: int
    baseline_false_satisfied: int
    assisted_false_satisfied: int
    baseline_rework_count: int
    assisted_rework_count: int
    is_outlier: bool
    outlier_reason: str
    quality_status: str
    quality_status_label: str
    reviewer: str
    note: str
    recorded_by: str
    created_at: str

    @property
    def evidence_complete(self) -> bool:
        return all(
            (
                self.participant,
                self.document_type,
                self.conditions,
                self.raw_record_url,
                self.gold_standard_url,
                self.reviewer,
            )
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.update(
            {
                "evidence_complete": self.evidence_complete,
                "time_saved_minutes": round(self.baseline_minutes - self.assisted_minutes, 2),
                "active_time_saved_minutes": round(
                    self.baseline_active_minutes - self.assisted_active_minutes, 2
                ),
                "omissions_reduced": self.baseline_omissions - self.assisted_omissions,
                "false_satisfied_reduced": (
                    self.baseline_false_satisfied - self.assisted_false_satisfied
                ),
                "rework_reduced": self.baseline_rework_count - self.assisted_rework_count,
            }
        )
        return payload


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
    experiment_id: str = "tendertrace-value-lab-v1",
    experiment_version: int = 1,
    participant: str = "",
    document_type: str = "",
    file_count: int = 1,
    sequence_order: str = "manual_first",
    conditions: str = "",
    source_url: str = "",
    raw_record_url: str = "",
    gold_standard_url: str = "",
    baseline_active_minutes: float | None = None,
    assisted_active_minutes: float | None = None,
    baseline_machine_wait_seconds: float = 0,
    assisted_machine_wait_seconds: float = 0,
    baseline_omissions: int = 0,
    assisted_omissions: int = 0,
    baseline_false_satisfied: int = 0,
    assisted_false_satisfied: int = 0,
    baseline_rework_count: int = 0,
    assisted_rework_count: int = 0,
    is_outlier: bool = False,
    outlier_reason: str = "",
) -> BusinessMeasurement:
    init_db(settings)
    values = {
        "task_type": task_type.strip(),
        "sample_ref": sample_ref.strip(),
        "experiment_id": experiment_id.strip(),
        "participant": participant.strip(),
        "document_type": document_type.strip(),
        "sequence_order": sequence_order.strip(),
        "conditions": conditions.strip(),
        "source_url": source_url.strip(),
        "raw_record_url": raw_record_url.strip(),
        "gold_standard_url": gold_standard_url.strip(),
        "quality_status": quality_status.strip(),
        "reviewer": reviewer.strip(),
        "note": note.strip(),
        "recorded_by": recorded_by.strip(),
        "outlier_reason": outlier_reason.strip(),
    }
    baseline = _positive_minutes(baseline_minutes, "baseline_minutes")
    assisted = _positive_minutes(assisted_minutes, "assisted_minutes")
    baseline_active = _nonnegative_minutes(
        baseline if baseline_active_minutes is None else baseline_active_minutes,
        "baseline_active_minutes",
        baseline,
    )
    assisted_active = _nonnegative_minutes(
        assisted if assisted_active_minutes is None else assisted_active_minutes,
        "assisted_active_minutes",
        assisted,
    )
    experiment_version_value = _positive_integer(experiment_version, "experiment_version")
    file_count_value = _positive_integer(file_count, "file_count")
    baseline_wait = _nonnegative_number(baseline_machine_wait_seconds, "baseline_machine_wait_seconds")
    assisted_wait = _nonnegative_number(assisted_machine_wait_seconds, "assisted_machine_wait_seconds")
    count_values = {
        "baseline_omissions": _nonnegative_integer(baseline_omissions, "baseline_omissions"),
        "assisted_omissions": _nonnegative_integer(assisted_omissions, "assisted_omissions"),
        "baseline_false_satisfied": _nonnegative_integer(
            baseline_false_satisfied, "baseline_false_satisfied"
        ),
        "assisted_false_satisfied": _nonnegative_integer(
            assisted_false_satisfied, "assisted_false_satisfied"
        ),
        "baseline_rework_count": _nonnegative_integer(
            baseline_rework_count, "baseline_rework_count"
        ),
        "assisted_rework_count": _nonnegative_integer(
            assisted_rework_count, "assisted_rework_count"
        ),
    }
    if not values["sample_ref"]:
        raise ValueError("sample_ref is required")
    if not values["experiment_id"]:
        raise ValueError("experiment_id is required")
    if values["task_type"] not in TASK_TYPE_LABELS:
        raise ValueError(f"unsupported task_type: {values['task_type']}")
    if values["sequence_order"] not in SEQUENCE_LABELS:
        raise ValueError(f"unsupported sequence_order: {values['sequence_order']}")
    if values["quality_status"] not in QUALITY_STATUS_LABELS:
        raise ValueError(f"unsupported quality_status: {values['quality_status']}")
    if values["quality_status"] != "not_reviewed" and not values["reviewer"]:
        raise ValueError("reviewer is required after quality review")
    if values["quality_status"] != "not_reviewed" and not values["gold_standard_url"]:
        raise ValueError("gold_standard_url is required after quality review")
    if values["quality_status"] == "passed":
        required = ("participant", "document_type", "conditions", "raw_record_url")
        missing = [field for field in required if not values[field]]
        if missing:
            raise ValueError(f"quality-passed measurement missing evidence: {', '.join(missing)}")
    for field in ("source_url", "raw_record_url", "gold_standard_url"):
        _validate_reference(values[field], field)
    if bool(is_outlier) and not values["outlier_reason"]:
        raise ValueError("outlier_reason is required when is_outlier is true")
    if not values["recorded_by"]:
        raise ValueError("recorded_by is required")
    measurement_id = _measurement_id(values["task_type"], values["sample_ref"])
    db_values = (
        measurement_id, values["task_type"], values["sample_ref"], values["experiment_id"],
        experiment_version_value, values["participant"], values["document_type"], file_count_value,
        values["sequence_order"], values["conditions"], values["source_url"], values["raw_record_url"],
        values["gold_standard_url"], baseline, assisted, baseline_active, assisted_active,
        baseline_wait, assisted_wait, count_values["baseline_omissions"],
        count_values["assisted_omissions"], count_values["baseline_false_satisfied"],
        count_values["assisted_false_satisfied"], count_values["baseline_rework_count"],
        count_values["assisted_rework_count"], int(bool(is_outlier)), values["outlier_reason"],
        values["quality_status"], values["reviewer"], values["note"], values["recorded_by"],
    )
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT INTO business_measurements(
                id, task_type, sample_ref, experiment_id, experiment_version,
                participant, document_type, file_count, sequence_order, conditions,
                source_url, raw_record_url, gold_standard_url,
                baseline_minutes, assisted_minutes,
                baseline_active_minutes, assisted_active_minutes,
                baseline_machine_wait_seconds, assisted_machine_wait_seconds,
                baseline_omissions, assisted_omissions,
                baseline_false_satisfied, assisted_false_satisfied,
                baseline_rework_count, assisted_rework_count,
                is_outlier, outlier_reason, quality_status, reviewer, note, recorded_by
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(task_type, sample_ref) DO UPDATE SET
                experiment_id = excluded.experiment_id,
                experiment_version = excluded.experiment_version,
                participant = excluded.participant,
                document_type = excluded.document_type,
                file_count = excluded.file_count,
                sequence_order = excluded.sequence_order,
                conditions = excluded.conditions,
                source_url = excluded.source_url,
                raw_record_url = excluded.raw_record_url,
                gold_standard_url = excluded.gold_standard_url,
                baseline_minutes = excluded.baseline_minutes,
                assisted_minutes = excluded.assisted_minutes,
                baseline_active_minutes = excluded.baseline_active_minutes,
                assisted_active_minutes = excluded.assisted_active_minutes,
                baseline_machine_wait_seconds = excluded.baseline_machine_wait_seconds,
                assisted_machine_wait_seconds = excluded.assisted_machine_wait_seconds,
                baseline_omissions = excluded.baseline_omissions,
                assisted_omissions = excluded.assisted_omissions,
                baseline_false_satisfied = excluded.baseline_false_satisfied,
                assisted_false_satisfied = excluded.assisted_false_satisfied,
                baseline_rework_count = excluded.baseline_rework_count,
                assisted_rework_count = excluded.assisted_rework_count,
                is_outlier = excluded.is_outlier,
                outlier_reason = excluded.outlier_reason,
                quality_status = excluded.quality_status,
                reviewer = excluded.reviewer,
                note = excluded.note,
                recorded_by = excluded.recorded_by
            """,
            db_values,
        )
        row = conn.execute("SELECT * FROM business_measurements WHERE id = ?", (measurement_id,)).fetchone()
        assert row is not None
        snapshot = _from_row(row)
        conn.execute(
            """
            INSERT INTO business_measurement_events(id, measurement_id, snapshot_json, actor)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid4()), measurement_id, json_dumps(snapshot.to_dict()), values["recorded_by"]),
        )
    return snapshot


def list_business_measurements(settings: Settings, *, limit: int = 500) -> list[BusinessMeasurement]:
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            "SELECT * FROM business_measurements ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (min(max(int(limit), 1), 1000),),
        ).fetchall()
    return [_from_row(row) for row in rows]


def business_measurement_summary(settings: Settings) -> dict[str, object]:
    items = list_business_measurements(settings)
    passed = [item for item in items if item.quality_status == "passed"]
    eligible = [item for item in passed if item.evidence_complete]
    baseline_total = round(sum(item.baseline_minutes for item in eligible), 2)
    assisted_total = round(sum(item.assisted_minutes for item in eligible), 2)
    saved_total = round(baseline_total - assisted_total, 2)
    claim_status = "measured" if len(eligible) >= MIN_GENERALIZATION_SAMPLE else "sample_only" if eligible else "not_measured"
    metrics = {
        "total_time": _paired_metric(eligible, "baseline_minutes", "assisted_minutes", "分钟"),
        "active_time": _paired_metric(eligible, "baseline_active_minutes", "assisted_active_minutes", "分钟"),
        "machine_wait": _paired_metric(eligible, "baseline_machine_wait_seconds", "assisted_machine_wait_seconds", "秒"),
        "omissions": _paired_metric(eligible, "baseline_omissions", "assisted_omissions", "项"),
        "false_satisfied": _paired_metric(eligible, "baseline_false_satisfied", "assisted_false_satisfied", "项"),
        "rework": _paired_metric(eligible, "baseline_rework_count", "assisted_rework_count", "次"),
    }
    measured_types = {item.task_type for item in eligible}
    return {
        "status": claim_status,
        "status_label": {
            "measured": "达到小样本展示门槛，仅陈述本批样本",
            "sample_only": "样本不足，仅展示原始结果，不做总体外推",
            "not_measured": "暂无完整配对实验，不能估算业务收益",
        }[claim_status],
        "generalization_allowed": False,
        "generalization_note": "实验结果只描述当前样本与参与人，不代表全部项目或未来收益。",
        "minimum_sample": MIN_GENERALIZATION_SAMPLE,
        "record_count": len(items),
        "eligible_sample_count": len(eligible),
        "quality_reviewed_count": sum(item.quality_status != "not_reviewed" for item in items),
        "quality_passed_count": len(passed),
        "quality_failed_count": sum(item.quality_status == "failed" for item in items),
        "incomplete_evidence_count": len(passed) - len(eligible),
        "outlier_count": sum(item.is_outlier for item in items),
        "participant_count": len({item.participant for item in items if item.participant}),
        "participants": sorted({item.participant for item in items if item.participant}),
        "document_types": sorted({item.document_type for item in items if item.document_type}),
        "file_count": sum(item.file_count for item in items),
        "conditions": sorted({item.conditions for item in items if item.conditions}),
        "baseline_minutes": baseline_total,
        "assisted_minutes": assisted_total,
        "saved_minutes": saved_total,
        "time_saving_rate": _ratio(saved_total, baseline_total),
        "median_saved_minutes": metrics["total_time"]["median_delta"],
        "metrics": metrics,
        "experiments": _experiment_summaries(items),
        "by_task_type": {
            task_type: _task_summary([item for item in eligible if item.task_type == task_type])
            for task_type in TASK_TYPE_LABELS
        },
        "direction_coverage": [
            {
                "direction": number,
                "name": name,
                "task_type": task_type,
                "task_type_label": "实验室本体" if task_type == "value_lab" else TASK_TYPE_LABELS[task_type],
                "sample_count": len(eligible) if task_type == "value_lab" else sum(item.task_type == task_type for item in eligible),
                "status": "active" if task_type == "value_lab" else "measured" if task_type in measured_types else "pending",
            }
            for number, name, task_type in DIRECTION_COVERAGE
        ],
        "formulas": _formula_descriptions(metrics),
        "items": [item.to_dict() for item in items],
        "note": "仅汇总质量复核通过、具备参与人、实验条件、原始记录和人工金标入口的配对样本。失败样本与异常值仍完整展示。",
        "protocol": {
            "recommended_sample_range": "5-10份公开招标文件",
            "pairing": "同一份文件执行人工基线与TenderTrace辅助处理",
            "sequence": "人工优先与辅助优先交叉分配，减少熟练度偏差",
            "time_fields": "机器等待时间、人工有效时间、总耗时分开记录",
            "quality_fields": "关键要求遗漏、错误满足判断、返工次数由人工金标核验",
            "engineering_separated": True,
            "raw_records_required": True,
            "failed_and_outliers_visible": True,
        },
    }


def _paired_metric(items: list[BusinessMeasurement], baseline_field: str, assisted_field: str, unit: str) -> dict[str, object]:
    baseline_values = [float(getattr(item, baseline_field)) for item in items]
    assisted_values = [float(getattr(item, assisted_field)) for item in items]
    deltas = [round(left - right, 2) for left, right in zip(baseline_values, assisted_values)]
    baseline_sum = round(sum(baseline_values), 2)
    assisted_sum = round(sum(assisted_values), 2)
    delta_sum = round(baseline_sum - assisted_sum, 2)
    return {
        "sample_count": len(items), "unit": unit,
        "baseline_sum": baseline_sum, "assisted_sum": assisted_sum, "delta_sum": delta_sum,
        "reduction_rate": _ratio(delta_sum, baseline_sum),
        "baseline_median": _median(baseline_values), "assisted_median": _median(assisted_values),
        "median_delta": _median(deltas), "baseline_range": _range(baseline_values),
        "assisted_range": _range(assisted_values), "delta_range": _range(deltas),
        "paired_values": [
            {"sample_ref": item.sample_ref, "baseline": baseline_values[index], "assisted": assisted_values[index], "delta": deltas[index], "is_outlier": item.is_outlier}
            for index, item in enumerate(items)
        ],
    }


def _formula_descriptions(metrics: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    labels = {
        "total_time": "总耗时降低率", "active_time": "人工有效时间降低率",
        "machine_wait": "机器等待时间变化率", "omissions": "关键要求遗漏降低率",
        "false_satisfied": "错误满足判断降低率", "rework": "返工次数降低率",
    }
    return [
        {"key": key, "label": labels[key], "formula": "(人工基线合计 - 系统辅助合计) ÷ 人工基线合计", "numerator": metric["delta_sum"], "denominator": metric["baseline_sum"], "result": metric["reduction_rate"], "unit": metric["unit"], "sample_count": metric["sample_count"]}
        for key, metric in metrics.items()
    ]


def _experiment_summaries(items: list[BusinessMeasurement]) -> list[dict[str, object]]:
    result = []
    for experiment_id, version in sorted({(item.experiment_id, item.experiment_version) for item in items}):
        group = [item for item in items if item.experiment_id == experiment_id and item.experiment_version == version]
        result.append({
            "experiment_id": experiment_id, "experiment_version": version, "sample_count": len(group),
            "eligible_sample_count": sum(item.quality_status == "passed" and item.evidence_complete for item in group),
            "participant_count": len({item.participant for item in group if item.participant}),
            "document_types": sorted({item.document_type for item in group if item.document_type}),
            "conditions": sorted({item.conditions for item in group if item.conditions}),
            "sequence_orders": sorted({item.sequence_order_label for item in group if item.sequence_order}),
        })
    return result


def _task_summary(items: list[BusinessMeasurement]) -> dict[str, object]:
    metric = _paired_metric(items, "baseline_minutes", "assisted_minutes", "分钟")
    return {"count": len(items), "baseline_minutes": metric["baseline_sum"], "assisted_minutes": metric["assisted_sum"], "saved_minutes": metric["delta_sum"], "time_saving_rate": metric["reduction_rate"], "median_saved_minutes": metric["median_delta"]}


def _positive_minutes(value: object, field: str) -> float:
    minutes = _number(value, field)
    if not 0 < minutes <= 24 * 60:
        raise ValueError(f"{field} must be greater than 0 and no more than 1440")
    return minutes


def _nonnegative_minutes(value: object, field: str, total: float) -> float:
    minutes = _number(value, field)
    if minutes < 0 or minutes > total:
        raise ValueError(f"{field} must be between 0 and total minutes")
    return minutes


def _number(value: object, field: str) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def _nonnegative_number(value: object, field: str) -> float:
    number = _number(value, field)
    if number < 0:
        raise ValueError(f"{field} must be zero or greater")
    return number


def _positive_integer(value: object, field: str) -> int:
    number = _nonnegative_integer(value, field)
    if number < 1:
        raise ValueError(f"{field} must be at least 1")
    return number


def _nonnegative_integer(value: object, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < 0:
        raise ValueError(f"{field} must be zero or greater")
    return number


def _validate_reference(value: str, field: str) -> None:
    if value and not (value.startswith("https://") or value.startswith("http://") or value.startswith("/")):
        raise ValueError(f"{field} must be an http(s) URL or an absolute application path")


def _median(values: list[float]) -> float | None:
    return round(float(median(values)), 2) if values else None


def _range(values: list[float]) -> dict[str, float] | None:
    return {"min": round(min(values), 2), "max": round(max(values), 2)} if values else None


def _ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator > 0 else None


def _measurement_id(task_type: str, sample_ref: str) -> str:
    return hashlib.sha256(f"{task_type}|{sample_ref}".encode()).hexdigest()[:24]


def _from_row(row: Any) -> BusinessMeasurement:
    task_type = str(row["task_type"] or "")
    quality_status = str(row["quality_status"] or "not_reviewed")
    sequence_order = str(row["sequence_order"] or "manual_first")
    return BusinessMeasurement(
        id=str(row["id"]), task_type=task_type, task_type_label=TASK_TYPE_LABELS.get(task_type, task_type),
        sample_ref=str(row["sample_ref"] or ""), experiment_id=str(row["experiment_id"] or "tendertrace-value-lab-v1"),
        experiment_version=int(row["experiment_version"] or 1), participant=str(row["participant"] or ""),
        document_type=str(row["document_type"] or ""), file_count=int(row["file_count"] or 1),
        sequence_order=sequence_order, sequence_order_label=SEQUENCE_LABELS.get(sequence_order, sequence_order),
        conditions=str(row["conditions"] or ""), source_url=str(row["source_url"] or ""),
        raw_record_url=str(row["raw_record_url"] or ""), gold_standard_url=str(row["gold_standard_url"] or ""),
        baseline_minutes=float(row["baseline_minutes"] or 0), assisted_minutes=float(row["assisted_minutes"] or 0),
        baseline_active_minutes=float(row["baseline_active_minutes"] or 0), assisted_active_minutes=float(row["assisted_active_minutes"] or 0),
        baseline_machine_wait_seconds=float(row["baseline_machine_wait_seconds"] or 0), assisted_machine_wait_seconds=float(row["assisted_machine_wait_seconds"] or 0),
        baseline_omissions=int(row["baseline_omissions"] or 0), assisted_omissions=int(row["assisted_omissions"] or 0),
        baseline_false_satisfied=int(row["baseline_false_satisfied"] or 0), assisted_false_satisfied=int(row["assisted_false_satisfied"] or 0),
        baseline_rework_count=int(row["baseline_rework_count"] or 0), assisted_rework_count=int(row["assisted_rework_count"] or 0),
        is_outlier=bool(row["is_outlier"]), outlier_reason=str(row["outlier_reason"] or ""),
        quality_status=quality_status, quality_status_label=QUALITY_STATUS_LABELS.get(quality_status, quality_status),
        reviewer=str(row["reviewer"] or ""), note=str(row["note"] or ""), recorded_by=str(row["recorded_by"] or ""),
        created_at=str(row["created_at"] or ""),
    )
