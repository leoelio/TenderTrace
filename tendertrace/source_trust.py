from __future__ import annotations

from typing import Any

from tendertrace.config import Settings
from tendertrace.source_map import build_source_map


def source_trust_profiles(settings: Settings) -> dict[str, dict[str, object]]:
    source_map = build_source_map(settings)
    profiles: dict[str, dict[str, object]] = {}
    for item in source_map.get("items", []):
        if not isinstance(item, dict):
            continue
        site = str(item.get("site") or "").strip()
        if not site:
            continue
        rules = _mapping(item.get("discovery_rules"))
        health = _mapping(item.get("health"))
        authority = str(rules.get("authority") or "").strip()
        source_class = str(rules.get("source_class") or "").strip()
        if not source_class:
            source_class = "official_primary" if authority else "unclassified"
        runs = _integer(health.get("runs"))
        profiles[site] = {
            "site": site,
            "authority": authority,
            "source_class": source_class,
            "engine": str(item.get("engine") or ""),
            "requires_login": bool(item.get("requires_login")),
            "observed_runs": runs,
            "reliability_score": (
                _ratio(health.get("reliability_score")) if runs > 0 else None
            ),
            "health_status": str(health.get("health_status") or "unknown"),
        }
    return profiles


def assess_notice_trust(
    payload: dict[str, Any],
    evidence: dict[str, Any],
    *,
    profiles: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    profiles = profiles or {}
    source_site = str(payload.get("source_site") or "").strip()
    profile = profiles.get(source_site, {})
    source_class = str(profile.get("source_class") or "unclassified")
    authority_points = {
        "official_primary": 25,
        "authenticated_aggregator": 14,
        "partner_signal": 10,
        "unclassified": 8,
    }.get(source_class, 8)

    observed_runs = _integer(profile.get("observed_runs"))
    observed_reliability = (
        _ratio(profile.get("reliability_score")) if observed_runs > 0 else None
    )
    reliability_points = (
        round(observed_reliability * 20) if observed_reliability is not None else 8
    )
    reliability_status = (
        str(profile.get("health_status") or "unknown")
        if observed_reliability is not None
        else "unobserved"
    )

    quality = _ratio(evidence.get("quality_score"))
    evidence_points = round(quality * 25)
    snapshot_ready = bool(str(evidence.get("snapshot_sha256") or "").strip())
    if snapshot_ready:
        evidence_points += 5

    source_sites = _source_sites(payload, evidence)
    source_count = len(source_sites)
    corroboration_points = 15 if source_count >= 3 else 10 if source_count == 2 else 0

    attachment_state, attachment_points, attachment_count = _attachment_assessment(
        payload,
        evidence,
    )
    score = min(
        100,
        authority_points
        + reliability_points
        + evidence_points
        + corroboration_points
        + attachment_points,
    )
    level = "high" if score >= 80 else "medium" if score >= 60 else "low"
    verification_status = _verification_status(
        evidence=evidence,
        snapshot_ready=snapshot_ready,
        source_class=source_class,
        source_count=source_count,
    )
    authority = str(profile.get("authority") or source_site or "来源未分类")
    reliability_text = (
        f"近 {observed_runs} 次采集可靠度 {observed_reliability:.0%}"
        if observed_reliability is not None
        else "暂无运行样本，未计为已验证可靠"
    )
    corroboration_text = (
        f"{source_count} 个独立来源交叉印证"
        if source_count >= 2
        else "单一来源，尚无跨源印证"
    )
    return {
        "score": score,
        "level": level,
        "level_label": {"high": "高可信", "medium": "中可信", "low": "待核验"}[level],
        "verification_status": verification_status,
        "verification_label": {
            "corroborated": "多源已印证",
            "source_verified": "官方证据已核验",
            "evidence_only": "单源证据已固化",
            "insufficient": "证据不足",
        }[verification_status],
        "source_site": source_site,
        "authority": authority,
        "source_class": source_class,
        "source_sites": source_sites,
        "source_count": source_count,
        "observed_reliability": {
            "status": reliability_status,
            "runs": observed_runs,
            "score": observed_reliability,
        },
        "attachment_evidence": {
            "status": attachment_state,
            "count": attachment_count,
        },
        "components": [
            _component("authority", "来源权威性", authority_points, 25, authority),
            _component(
                "reliability",
                "采集可靠性",
                reliability_points,
                20,
                reliability_text,
                status=reliability_status,
            ),
            _component(
                "grounding",
                "原文证据",
                evidence_points,
                30,
                f"事实一致性 {quality:.0%}" + ("，快照已固化" if snapshot_ready else "，缺少快照哈希"),
            ),
            _component(
                "corroboration",
                "跨源印证",
                corroboration_points,
                15,
                corroboration_text,
            ),
            _component(
                "attachments",
                "附件证据",
                attachment_points,
                10,
                _attachment_text(attachment_state, attachment_count),
                status=attachment_state,
            ),
        ],
        "basis": [
            f"来源：{authority}",
            reliability_text,
            corroboration_text,
            _attachment_text(attachment_state, attachment_count),
        ],
        "engine": "tendertrace_source_trust_v1",
    }


def _source_sites(payload: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    sites: set[str] = set()
    primary = str(payload.get("source_site") or "").strip()
    if primary:
        sites.add(primary)
    raw_sites = payload.get("source_sites")
    if isinstance(raw_sites, list):
        sites.update(str(value).strip() for value in raw_sites if str(value).strip())
    for container in (payload.get("related_sources"), evidence.get("related_sources")):
        if not isinstance(container, list):
            continue
        for item in container:
            if isinstance(item, dict):
                site = str(item.get("source_site") or "").strip()
                if site:
                    sites.add(site)
    return sorted(sites)


def _attachment_assessment(
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[str, int, int]:
    snapshots = payload.get("attachment_snapshots")
    snapshot_rows = [item for item in snapshots if isinstance(item, dict)] if isinstance(snapshots, list) else []
    extracted = [
        item
        for item in snapshot_rows
        if str(item.get("status") or "") in {"downloaded", "extracted", "passed"}
        and (str(item.get("sha256") or "") or _integer(item.get("text_length")) > 0)
    ]
    if extracted:
        return "verified", 10, len(extracted)
    attachments = evidence.get("attachments") or payload.get("attachments")
    linked = len(attachments) if isinstance(attachments, list) else 0
    if linked:
        return "linked", 4, linked
    return "missing", 0, 0


def _verification_status(
    *,
    evidence: dict[str, Any],
    snapshot_ready: bool,
    source_class: str,
    source_count: int,
) -> str:
    evidence_passed = str(evidence.get("status") or "") == "passed"
    if evidence_passed and snapshot_ready and source_count >= 2:
        return "corroborated"
    if evidence_passed and snapshot_ready and source_class == "official_primary":
        return "source_verified"
    if snapshot_ready:
        return "evidence_only"
    return "insufficient"


def _component(
    key: str,
    label: str,
    score: int,
    maximum: int,
    evidence: str,
    *,
    status: str = "measured",
) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "score": score,
        "maximum": maximum,
        "status": status,
        "evidence": evidence,
    }


def _attachment_text(status: str, count: int) -> str:
    if status == "verified":
        return f"{count} 个附件已下载并固化证据"
    if status == "linked":
        return f"{count} 个附件链接待下载核验"
    return "未发现可核验附件"


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _ratio(value: object) -> float:
    try:
        return max(0.0, min(float(value), 1.0))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
