from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from typing import Any
import httpx

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.intent.topic import extract_topic
from tendertrace.opportunity_radar import CHINA_LOCATIONS, DOMESTIC_SOURCES


USGS_MONTH_FEED = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.geojson"
)
VALID_SCOPES = {"china", "global"}
VALID_LAYERS = {"opportunity", "award", "flow", "external"}

CHINA_CENTROIDS: dict[str, tuple[float, float, str]] = {
    "beijing": (39.9042, 116.4074, "CN"),
    "tianjin": (39.3434, 117.3616, "CN"),
    "hebei": (38.0428, 114.5149, "CN"),
    "shanxi": (37.8706, 112.5489, "CN"),
    "inner-mongolia": (40.8174, 111.7656, "CN"),
    "liaoning": (41.8057, 123.4315, "CN"),
    "jilin": (43.8171, 125.3235, "CN"),
    "heilongjiang": (45.8038, 126.5349, "CN"),
    "shanghai": (31.2304, 121.4737, "CN"),
    "jiangsu": (32.0603, 118.7969, "CN"),
    "zhejiang": (30.2741, 120.1551, "CN"),
    "anhui": (31.8206, 117.2272, "CN"),
    "fujian": (26.0745, 119.2965, "CN"),
    "jiangxi": (28.6829, 115.8582, "CN"),
    "shandong": (36.6512, 117.1201, "CN"),
    "henan": (34.7466, 113.6254, "CN"),
    "hubei": (30.5928, 114.3055, "CN"),
    "hunan": (28.2282, 112.9388, "CN"),
    "guangdong": (23.1291, 113.2644, "CN"),
    "guangxi": (22.8170, 108.3669, "CN"),
    "hainan": (20.0440, 110.1999, "CN"),
    "chongqing": (29.4316, 106.9123, "CN"),
    "sichuan": (30.5728, 104.0668, "CN"),
    "guizhou": (26.6470, 106.6302, "CN"),
    "yunnan": (25.0389, 102.7183, "CN"),
    "tibet": (29.6520, 91.1721, "CN"),
    "shaanxi": (34.3416, 108.9398, "CN"),
    "gansu": (36.0611, 103.8343, "CN"),
    "qinghai": (36.6171, 101.7782, "CN"),
    "ningxia": (38.4872, 106.2309, "CN"),
    "xinjiang": (43.8256, 87.6168, "CN"),
    "hong-kong": (22.3193, 114.1694, "CN"),
    "macao": (22.1987, 113.5439, "CN"),
    "taiwan": (23.6978, 120.9605, "CN"),
}

WORLD_PLACES: tuple[dict[str, object], ...] = (
    {"name": "Taiwan", "code": "CN", "aliases": ("Taiwan", "Hualien", "台湾", "花莲"), "lat": 23.6978, "lon": 120.9605},
    {"name": "China", "code": "CN", "aliases": ("China", "中国"), "lat": 35.8617, "lon": 104.1954},
    {"name": "Philippines", "code": "PH", "aliases": ("Philippines", "菲律宾"), "lat": 12.8797, "lon": 121.7740},
    {"name": "Indonesia", "code": "ID", "aliases": ("Indonesia", "印度尼西亚"), "lat": -0.7893, "lon": 113.9213},
    {"name": "Canada", "code": "CA", "aliases": ("Canada", "Ontario", "加拿大"), "lat": 56.1304, "lon": -106.3468},
    {"name": "Uruguay", "code": "UY", "aliases": ("Uruguay", "乌拉圭"), "lat": -32.5228, "lon": -55.7658},
    {"name": "Mozambique", "code": "MZ", "aliases": ("Mozambique", "莫桑比克"), "lat": -18.6657, "lon": 35.5296},
    {"name": "United Kingdom", "code": "GB", "aliases": ("United Kingdom", "UKC", "UKD", "Lancaster", "Tyneside", "英国"), "lat": 55.3781, "lon": -3.4360},
    {"name": "Netherlands", "code": "NL", "aliases": ("NLD", "Netherlands", "荷兰"), "lat": 52.1326, "lon": 5.2913},
    {"name": "Romania", "code": "RO", "aliases": ("ROU", "Romania", "罗马尼亚"), "lat": 45.9432, "lon": 24.9668},
    {"name": "Germany", "code": "DE", "aliases": ("DEU", "Germany", "德国"), "lat": 51.1657, "lon": 10.4515},
    {"name": "Ukraine", "code": "UA", "aliases": ("Ukraine", "乌克兰"), "lat": 48.3794, "lon": 31.1656},
    {"name": "Japan", "code": "JP", "aliases": ("Japan", "日本"), "lat": 36.2048, "lon": 138.2529},
    {"name": "Russia", "code": "RU", "aliases": ("Russia", "俄罗斯"), "lat": 61.5240, "lon": 105.3188},
    {"name": "Yemen", "code": "YE", "aliases": ("Yemen", "也门"), "lat": 15.5527, "lon": 48.5164},
)

CITY_ALIASES = {
    "成都": "sichuan",
    "杭州": "zhejiang",
    "宁波": "zhejiang",
    "苏州": "jiangsu",
    "南京": "jiangsu",
    "广州": "guangdong",
    "深圳": "guangdong",
    "济南": "shandong",
    "青岛": "shandong",
    "武汉": "hubei",
    "西安": "shaanxi",
}


def sync_business_events(settings: Settings) -> dict[str, int]:
    """Normalize the existing notice index into map events without external fetching."""
    init_db(settings)
    with connection(settings) as conn:
        rows = conn.execute(
            """
            SELECT id, source_site, source_url, title, publish_time, region, purchaser,
                   content_text, core_content, fields_json, last_seen_at, updated_at
            FROM notices
            WHERE source_site <> '' AND source_site <> 'demo'
            ORDER BY COALESCE(publish_time, created_at), rowid
            """
        ).fetchall()
        companies = {
            str(row["legal_name"]): str(row["region"] or "")
            for row in conn.execute("SELECT legal_name, region FROM company_entities")
        }
        event_count = 0
        award_count = 0
        flow_count = 0
        for row in rows:
            fields = _json_object(row["fields_json"])
            content = " ".join(
                str(value or "")
                for value in (row["title"], row["content_text"], row["core_content"])
            )
            location = resolve_business_location(
                str(row["region"] or ""), str(row["source_site"] or "")
            )
            category = _category(str(row["title"] or ""), content, fields)
            event_type = "award" if _is_award(content, fields) else "opportunity"
            supplier = _supplier_name(content)
            amount, currency = _amount(content)
            event_id = _stable_id("geo", event_type, str(row["id"]))
            conn.execute(
                """
                INSERT INTO geo_events(
                    id, event_type, object_type, object_id, notice_id, title, category,
                    region_name, country_code, latitude, longitude, china_x, china_y,
                    world_x, world_y, coordinate_precision, event_time, source_name,
                    source_url, source_license, evidence_status, amount, currency,
                    counterparty, payload_json, captured_at, updated_at
                ) VALUES (?, ?, 'notice', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(event_type, object_type, object_id) DO UPDATE SET
                    title=excluded.title, category=excluded.category,
                    region_name=excluded.region_name, country_code=excluded.country_code,
                    latitude=excluded.latitude, longitude=excluded.longitude,
                    china_x=excluded.china_x, china_y=excluded.china_y,
                    world_x=excluded.world_x, world_y=excluded.world_y,
                    coordinate_precision=excluded.coordinate_precision,
                    event_time=excluded.event_time, source_url=excluded.source_url,
                    evidence_status=excluded.evidence_status, amount=excluded.amount,
                    currency=excluded.currency, counterparty=excluded.counterparty,
                    payload_json=excluded.payload_json, updated_at=datetime('now')
                """,
                (
                    event_id,
                    event_type,
                    str(row["id"]),
                    str(row["id"]),
                    str(row["title"] or ""),
                    category,
                    location["name"],
                    location["country_code"],
                    location["latitude"],
                    location["longitude"],
                    location["china_x"],
                    location["china_y"],
                    location["world_x"],
                    location["world_y"],
                    location["precision"],
                    str(row["publish_time"] or row["updated_at"] or ""),
                    str(row["source_site"] or ""),
                    str(row["source_url"] or ""),
                    "existing_notice_source",
                    str(fields.get("evidence_status") or "indexed"),
                    amount,
                    currency,
                    supplier or str(row["purchaser"] or ""),
                    json_dumps({"purchaser": str(row["purchaser"] or ""), "supplier": supplier}),
                    str(row["last_seen_at"] or row["updated_at"] or ""),
                ),
            )
            event_count += 1
            if event_type == "award":
                award_count += 1
                supplier_region = companies.get(supplier, "") if supplier else ""
                if supplier and supplier_region:
                    destination = resolve_business_location(supplier_region, "")
                    flow_id = _stable_id("flow", str(row["id"]), supplier)
                    conn.execute(
                        """
                        INSERT INTO business_flows(
                            id, notice_id, flow_type, from_label, from_latitude,
                            from_longitude, from_china_x, from_china_y, from_world_x,
                            from_world_y, from_precision, to_label, to_latitude,
                            to_longitude, to_china_x, to_china_y, to_world_x, to_world_y,
                            to_precision, amount, currency, occurred_at, source_name,
                            source_url, source_license, evidence_status, payload_json,
                            captured_at, updated_at
                        ) VALUES (?, ?, 'award', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(notice_id, flow_type, from_label, to_label) DO UPDATE SET
                            amount=excluded.amount, currency=excluded.currency,
                            occurred_at=excluded.occurred_at, evidence_status=excluded.evidence_status,
                            payload_json=excluded.payload_json, updated_at=datetime('now')
                        """,
                        (
                            flow_id,
                            str(row["id"]),
                            str(row["purchaser"] or location["name"]),
                            location["latitude"],
                            location["longitude"],
                            location["china_x"],
                            location["china_y"],
                            location["world_x"],
                            location["world_y"],
                            location["precision"],
                            supplier,
                            destination["latitude"],
                            destination["longitude"],
                            destination["china_x"],
                            destination["china_y"],
                            destination["world_x"],
                            destination["world_y"],
                            destination["precision"],
                            amount,
                            currency,
                            str(row["publish_time"] or row["updated_at"] or ""),
                            str(row["source_site"] or ""),
                            str(row["source_url"] or ""),
                            "existing_notice_source",
                            str(fields.get("evidence_status") or "indexed"),
                            json_dumps({"category": category, "title": str(row["title"] or "")}),
                            str(row["last_seen_at"] or row["updated_at"] or ""),
                        ),
                    )
                    flow_count += 1
    return {"geo_events": event_count, "awards": award_count, "flows": flow_count}


def fetch_usgs_external_events(
    settings: Settings,
    *,
    limit: int = 60,
    timeout: float = 20.0,
) -> dict[str, object]:
    """Fetch the official USGS M4.5+ monthly GeoJSON feed on explicit request."""
    init_db(settings)
    response = httpx.get(USGS_MONTH_FEED, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features") if isinstance(payload, dict) else []
    imported: list[str] = []
    for raw in list(features or [])[: max(1, min(int(limit), 200))]:
        if not isinstance(raw, dict):
            continue
        props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
        geometry = raw.get("geometry") if isinstance(raw.get("geometry"), dict) else {}
        coordinates = geometry.get("coordinates") if isinstance(geometry.get("coordinates"), list) else []
        if len(coordinates) < 2:
            continue
        source_event_id = str(raw.get("id") or "").strip()
        if not source_event_id:
            continue
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
        magnitude = float(props.get("mag") or 0)
        place = str(props.get("place") or "Earthquake")
        event_time = _epoch_iso(props.get("time"))
        source_url = str(props.get("url") or props.get("detail") or USGS_MONTH_FEED)
        raw_json = json_dumps(raw)
        snapshot = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        country = _world_place(place)
        event_id = _stable_id("external", "usgs", source_event_id)
        severity = "critical" if magnitude >= 7 else "high" if magnitude >= 6 else "watch" if magnitude >= 5 else "info"
        radius = 900 if magnitude >= 7 else 650 if magnitude >= 6 else 400 if magnitude >= 5 else 250
        with connection(settings) as conn:
            conn.execute(
                """
                INSERT INTO external_events(
                    id, source_event_id, event_type, title, summary, severity,
                    magnitude, region_name, country_code, latitude, longitude,
                    world_x, world_y, coordinate_precision, impact_radius_km,
                    event_time, source_name, source_url, source_license,
                    access_policy, access_frequency, evidence_status,
                    snapshot_sha256, raw_json, captured_at, updated_at
                ) VALUES (?, ?, 'earthquake', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'exact', ?, ?, 'USGS', ?, 'USGS public domain', 'public', 'minute_geojson_feed', ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(source_name, source_event_id) DO UPDATE SET
                    title=excluded.title, summary=excluded.summary,
                    severity=excluded.severity, magnitude=excluded.magnitude,
                    region_name=excluded.region_name, country_code=excluded.country_code,
                    latitude=excluded.latitude, longitude=excluded.longitude,
                    world_x=excluded.world_x, world_y=excluded.world_y,
                    impact_radius_km=excluded.impact_radius_km,
                    event_time=excluded.event_time, source_url=excluded.source_url,
                    evidence_status=excluded.evidence_status,
                    snapshot_sha256=excluded.snapshot_sha256, raw_json=excluded.raw_json,
                    updated_at=datetime('now')
                """,
                (
                    event_id,
                    source_event_id,
                    f"M{magnitude:.1f} · {place}",
                    "USGS 实时 GeoJSON 事件。事件存在不等于 TenderTrace 项目已经受影响。",
                    severity,
                    magnitude,
                    place,
                    str(country.get("country_code") or ""),
                    latitude,
                    longitude,
                    _world_xy(latitude, longitude)[0],
                    _world_xy(latitude, longitude)[1],
                    radius,
                    event_time,
                    source_url,
                    "verified_source" if str(props.get("status") or "").casefold() == "reviewed" else "candidate",
                    snapshot,
                    raw_json,
                ),
            )
        imported.append(event_id)
    return {
        "source": "USGS",
        "source_url": USGS_MONTH_FEED,
        "source_generated_at": _epoch_iso((payload.get("metadata") or {}).get("generated")),
        "feed_count": int((payload.get("metadata") or {}).get("count") or len(features or [])),
        "imported_count": len(imported),
        "event_ids": imported,
    }


def evaluate_external_event_impacts(
    settings: Settings,
    external_event_id: str,
    *,
    actor: str = "admin",
) -> dict[str, object]:
    init_db(settings)
    with connection(settings) as conn:
        external = conn.execute(
            "SELECT * FROM external_events WHERE id = ?", (external_event_id,)
        ).fetchone()
        if external is None:
            raise LookupError("external event not found")
        targets = conn.execute(
            "SELECT * FROM geo_events WHERE event_type IN ('opportunity', 'award')"
        ).fetchall()
        flows = conn.execute("SELECT * FROM business_flows").fetchall()
        created = 0
        for target in targets:
            match = _impact_match(external, target)
            if match is None:
                continue
            link_id = _stable_id("impact", external_event_id, "notice", str(target["object_id"]))
            conn.execute(
                """
                INSERT INTO impact_links(
                    id, external_event_id, target_type, target_id, target_title,
                    relation_basis, rule_key, match_basis_json, impact_scope,
                    severity, confidence, explanation, suggested_action,
                    review_status, updated_at
                ) VALUES (?, ?, 'notice', ?, ?, 'rule', ?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
                ON CONFLICT(external_event_id, target_type, target_id, rule_key) DO UPDATE SET
                    match_basis_json=excluded.match_basis_json,
                    impact_scope=excluded.impact_scope, severity=excluded.severity,
                    confidence=excluded.confidence, explanation=excluded.explanation,
                    suggested_action=excluded.suggested_action, updated_at=datetime('now')
                """,
                (
                    link_id,
                    external_event_id,
                    str(target["object_id"]),
                    str(target["title"]),
                    str(match["rule_key"]),
                    json_dumps(match["basis"]),
                    f"地区：{target['region_name']}；品类：{target['category'] or '待核'}",
                    _impact_severity(str(external["severity"])),
                    int(match["confidence"]),
                    str(match["explanation"]),
                    "核验项目交付地点、合作方所在地与运输路径；确认前不修改原项目结论。",
                ),
            )
            created += 1
        for flow in flows:
            match = _flow_impact_match(external, flow)
            if match is None:
                continue
            link_id = _stable_id("impact", external_event_id, "flow", str(flow["id"]))
            conn.execute(
                """
                INSERT INTO impact_links(
                    id, external_event_id, target_type, target_id, target_title,
                    relation_basis, rule_key, match_basis_json, impact_scope,
                    severity, confidence, explanation, suggested_action,
                    review_status, updated_at
                ) VALUES (?, ?, 'flow', ?, ?, 'rule', ?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
                ON CONFLICT(external_event_id, target_type, target_id, rule_key) DO UPDATE SET
                    match_basis_json=excluded.match_basis_json,
                    impact_scope=excluded.impact_scope, severity=excluded.severity,
                    confidence=excluded.confidence, explanation=excluded.explanation,
                    suggested_action=excluded.suggested_action, updated_at=datetime('now')
                """,
                (
                    link_id,
                    external_event_id,
                    str(flow["id"]),
                    f"{flow['from_label']} → {flow['to_label']}",
                    str(match["rule_key"]),
                    json_dumps(match["basis"]),
                    "交易或交付路径",
                    _impact_severity(str(external["severity"])),
                    int(match["confidence"]),
                    str(match["explanation"]),
                    "由供应链负责人确认实际运输路径、替代路线和交期缓冲。",
                ),
            )
            created += 1
    return {
        "external_event_id": external_event_id,
        "candidate_impact_count": created,
        "review_status": "pending",
        "actor": actor,
        "rule_version": "external-region-distance-v1",
    }


def review_impact_link(
    settings: Settings,
    impact_id: str,
    *,
    status: str,
    actor: str,
    note: str,
) -> dict[str, object]:
    if status not in {"confirmed", "rejected", "monitoring"}:
        raise ValueError("status must be confirmed, rejected or monitoring")
    if not str(note).strip():
        raise ValueError("review note is required")
    with connection(settings) as conn:
        row = conn.execute("SELECT id FROM impact_links WHERE id = ?", (impact_id,)).fetchone()
        if row is None:
            raise LookupError("impact link not found")
        conn.execute(
            """
            UPDATE impact_links
            SET review_status = ?, review_note = ?, reviewed_by = ?,
                reviewed_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, str(note).strip(), actor, impact_id),
        )
        updated = conn.execute("SELECT * FROM impact_links WHERE id = ?", (impact_id,)).fetchone()
    return _impact_payload(updated)


def build_battle_map(
    settings: Settings,
    *,
    scope: str = "global",
    window_hours: int = 2160,
    category: str = "",
    layers: list[str] | None = None,
    mode: str = "live",
) -> dict[str, object]:
    init_db(settings)
    scope = scope if scope in VALID_SCOPES else "global"
    window_hours = max(0, min(int(window_hours), 24 * 3650))
    category = " ".join(str(category).split())[:80]
    selected_layers = [item for item in (layers or sorted(VALID_LAYERS)) if item in VALID_LAYERS]
    if mode == "replay":
        replay = latest_battle_map_replay(
            settings, scope=scope, window_hours=window_hours, category=category
        )
        if replay:
            payload = replay["payload"]
            payload["mode"] = "replay"
            payload["replay"] = {key: replay[key] for key in ("id", "data_as_of", "state_hash", "verified", "verified_at")}
            return payload
    sync_business_events(settings)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours) if window_hours else None
    with connection(settings) as conn:
        geo_rows = conn.execute("SELECT * FROM geo_events ORDER BY event_time DESC, id").fetchall()
        flow_rows = conn.execute("SELECT * FROM business_flows ORDER BY occurred_at DESC, id").fetchall()
        external_rows = conn.execute("SELECT * FROM external_events ORDER BY event_time DESC, id").fetchall()
        impact_rows = conn.execute("SELECT * FROM impact_links ORDER BY updated_at DESC, id").fetchall()
    geo_events = [_geo_payload(row, scope) for row in geo_rows]
    geo_events = [item for item in geo_events if _event_visible(item, scope, cutoff, category)]
    flows = [_flow_payload(row, scope) for row in flow_rows]
    flows = [item for item in flows if _time_visible(str(item["event_time"]), cutoff)]
    external_events = [_external_payload(row, scope) for row in external_rows]
    external_events = [item for item in external_events if _time_visible(str(item["event_time"]), cutoff)]
    if scope == "china":
        external_events = [item for item in external_events if item["country_code"] == "CN"]
    impacts = [_impact_payload(row) for row in impact_rows]
    visible_ids = {str(item["id"]) for item in external_events}
    impacts = [item for item in impacts if str(item["external_event_id"]) in visible_ids]
    if "opportunity" not in selected_layers:
        geo_events = [item for item in geo_events if item["layer"] != "opportunity"]
    if "award" not in selected_layers:
        geo_events = [item for item in geo_events if item["layer"] != "award"]
    if "flow" not in selected_layers:
        flows = []
    if "external" not in selected_layers:
        external_events = []
        impacts = []
    visible_target_ids = {str(item["object_id"]) for item in geo_events} | {str(item["id"]) for item in flows}
    impacts = [item for item in impacts if str(item["target_id"]) in visible_target_ids]
    cards = _impact_cards(external_events, impacts, geo_events, flows)
    timeline = _timeline(geo_events, external_events)
    clusters = _clusters(geo_events, external_events)
    mapped_domestic = [item for item in geo_events if item["country_code"] == "CN"]
    province_eligible = [item for item in mapped_domestic if item["coordinate_precision"] != "country"]
    province_domestic = [item for item in province_eligible if item["coordinate_precision"] in {"province", "city", "exact"}]
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data_times = [str(item["captured_at"]) for item in geo_events + external_events if item.get("captured_at")]
    summary = {
        "event_count": len(geo_events) + len(external_events),
        "opportunity_count": sum(item["layer"] == "opportunity" for item in geo_events),
        "award_count": sum(item["layer"] == "award" for item in geo_events),
        "flow_count": len(flows),
        "external_event_count": len(external_events),
        "candidate_impact_count": len(impacts),
        "confirmed_impact_count": sum(item["review_status"] == "confirmed" for item in impacts),
        "cluster_count": len(clusters),
        "domestic_geocoded_rate": round(sum(item["coordinate_precision"] != "unknown" for item in mapped_domestic) / len(mapped_domestic), 3) if mapped_domestic else 1.0,
        "province_precision_rate": round(len(province_domestic) / len(province_eligible), 3) if province_eligible else 1.0,
        "country_level_count": sum(item["coordinate_precision"] == "country" for item in mapped_domestic),
    }
    payload: dict[str, object] = {
        "mode": "live",
        "scope": scope,
        "window_hours": window_hours,
        "category": category,
        "layers": selected_layers,
        "generated_at": generated_at,
        "data_as_of": max(data_times, default=generated_at),
        "last_connected_at": generated_at,
        "summary": summary,
        "clusters": clusters,
        "events": geo_events,
        "flows": flows,
        "external_events": external_events,
        "impacts": impacts,
        "impact_cards": cards,
        "timeline": timeline,
        "available_categories": _counter_items(Counter(str(item["category"]) for item in geo_events if item["category"])),
        "legend": {
            "opportunity": "蓝色圆点：真实公告机会",
            "award": "绿色菱形：真实成交或合同公告",
            "flow": "弧线：有双方位置依据的交易流向",
            "external": "橙红波纹：权威外部事件候选",
            "impact": "影响关系分为直接证据、规则关联和人工判断",
        },
        "rules": {
            "random_points_forbidden": True,
            "map_and_list_share_query": True,
            "external_event_is_not_impact": True,
            "human_confirmation_required": True,
            "coordinate_precision_visible": True,
            "offline_replay_supported": True,
            "motion_can_be_disabled": True,
        },
        "replay": {},
    }
    return payload


def save_battle_map_replay(
    settings: Settings,
    *,
    scope: str,
    window_hours: int,
    category: str = "",
    actor: str = "admin",
    verified: bool = True,
) -> dict[str, object]:
    payload = build_battle_map(
        settings,
        scope=scope,
        window_hours=window_hours,
        category=category,
        mode="live",
    )
    stored = {key: value for key, value in payload.items() if key != "replay"}
    serialized = json_dumps(stored)
    state_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    frame_id = _stable_id("replay", scope, str(window_hours), category, state_hash)
    with connection(settings) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO map_replay_frames(
                id, scope, window_hours, category, data_as_of, state_hash,
                payload_json, verified, verified_by, verified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? THEN datetime('now') END)
            """,
            (
                frame_id,
                scope,
                int(window_hours),
                category,
                str(payload["data_as_of"]),
                state_hash,
                serialized,
                int(verified),
                actor if verified else None,
                int(verified),
            ),
        )
    return latest_battle_map_replay(settings, scope=scope, window_hours=window_hours, category=category) or {}


def latest_battle_map_replay(
    settings: Settings,
    *,
    scope: str,
    window_hours: int,
    category: str = "",
) -> dict[str, object] | None:
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT * FROM map_replay_frames
            WHERE scope = ? AND window_hours = ? AND category = ? AND verified = 1
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (scope, int(window_hours), category),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "scope": str(row["scope"]),
        "window_hours": int(row["window_hours"]),
        "category": str(row["category"]),
        "data_as_of": str(row["data_as_of"]),
        "state_hash": str(row["state_hash"]),
        "verified": bool(row["verified"]),
        "verified_at": str(row["verified_at"] or ""),
        "created_at": str(row["created_at"]),
        "payload": _json_object(row["payload_json"]),
    }


def battle_map_event_detail(settings: Settings, event_id: str) -> dict[str, object]:
    with connection(settings) as conn:
        geo = conn.execute("SELECT * FROM geo_events WHERE id = ?", (event_id,)).fetchone()
        if geo is not None:
            return {"kind": "business_event", "event": _geo_payload(geo, "global")}
        external = conn.execute("SELECT * FROM external_events WHERE id = ?", (event_id,)).fetchone()
        if external is not None:
            impacts = conn.execute(
                "SELECT * FROM impact_links WHERE external_event_id = ? ORDER BY confidence DESC",
                (event_id,),
            ).fetchall()
            return {
                "kind": "external_event",
                "event": _external_payload(external, "global"),
                "impacts": [_impact_payload(row) for row in impacts],
            }
        flow = conn.execute("SELECT * FROM business_flows WHERE id = ?", (event_id,)).fetchone()
        if flow is not None:
            return {"kind": "business_flow", "event": _flow_payload(flow, "global")}
    raise LookupError("battle map event not found")


def battle_map_revision(settings: Settings) -> dict[str, object]:
    with connection(settings) as conn:
        values = []
        for table in ("geo_events", "business_flows", "external_events", "impact_links"):
            row = conn.execute(
                f"SELECT COUNT(*) AS count, MAX(updated_at) AS updated_at FROM {table}"
            ).fetchone()
            values.append(f"{table}:{row['count']}:{row['updated_at'] or ''}")
    signature = "|".join(values)
    return {
        "revision": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def resolve_business_location(region: str, source_site: str) -> dict[str, object]:
    value = str(region or "").strip()
    folded = value.casefold()
    for city, location_id in CITY_ALIASES.items():
        if city in value:
            location = next(item for item in CHINA_LOCATIONS if item["id"] == location_id)
            return _china_location(location, precision="city", label=value)
    for location in CHINA_LOCATIONS:
        if any(str(alias).casefold() in folded for alias in location["aliases"]):
            return _china_location(location, precision="province", label=str(location["name"]))
    if source_site in DOMESTIC_SOURCES or value in {"全国", "中国", ""}:
        return {
            "name": value or "全国",
            "country_code": "CN",
            "latitude": 35.8617,
            "longitude": 104.1954,
            "china_x": 50.0,
            "china_y": 48.0,
            "world_x": 79.0,
            "world_y": 34.0,
            "precision": "country",
        }
    place = _world_place(value)
    if place:
        return place
    return {
        "name": value or "地区待核",
        "country_code": "",
        "latitude": None,
        "longitude": None,
        "china_x": None,
        "china_y": None,
        "world_x": 50.0,
        "world_y": 50.0,
        "precision": "unknown",
    }


def _china_location(location: dict[str, object], *, precision: str, label: str) -> dict[str, object]:
    lat, lon, code = CHINA_CENTROIDS[str(location["id"])]
    world_x, world_y = _world_xy(lat, lon)
    return {
        "name": label,
        "country_code": code,
        "latitude": lat,
        "longitude": lon,
        "china_x": float(location["x"]),
        "china_y": float(location["y"]),
        "world_x": world_x,
        "world_y": world_y,
        "precision": precision,
    }


def _world_place(value: str) -> dict[str, object]:
    folded = str(value or "").casefold()
    for item in WORLD_PLACES:
        if any(str(alias).casefold() in folded for alias in item["aliases"]):
            lat = float(item["lat"])
            lon = float(item["lon"])
            world_x, world_y = _world_xy(lat, lon)
            return {
                "name": str(item["name"]),
                "country_code": str(item["code"]),
                "latitude": lat,
                "longitude": lon,
                "china_x": None,
                "china_y": None,
                "world_x": world_x,
                "world_y": world_y,
                "precision": "country",
            }
    return {}


def _world_xy(latitude: float, longitude: float) -> tuple[float, float]:
    return (
        round(max(3.0, min(97.0, (float(longitude) + 180.0) / 360.0 * 100.0)), 3),
        round(max(5.0, min(95.0, (90.0 - float(latitude)) / 180.0 * 100.0)), 3),
    )


def _geo_payload(row: Any, scope: str) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "layer": str(row["event_type"]),
        "object_type": str(row["object_type"]),
        "object_id": str(row["object_id"]),
        "notice_id": str(row["notice_id"] or ""),
        "title": str(row["title"]),
        "category": str(row["category"]),
        "region_name": str(row["region_name"]),
        "country_code": str(row["country_code"]),
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "map_x": row["china_x"] if scope == "china" else row["world_x"],
        "map_y": row["china_y"] if scope == "china" else row["world_y"],
        "coordinate_precision": str(row["coordinate_precision"]),
        "event_time": str(row["event_time"]),
        "source_name": str(row["source_name"]),
        "source_url": str(row["source_url"]),
        "source_license": str(row["source_license"]),
        "evidence_status": str(row["evidence_status"]),
        "amount": row["amount"],
        "currency": str(row["currency"]),
        "counterparty": str(row["counterparty"]),
        "captured_at": str(row["captured_at"]),
    }


def _flow_payload(row: Any, scope: str) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "layer": "flow",
        "notice_id": str(row["notice_id"]),
        "flow_type": str(row["flow_type"]),
        "from_label": str(row["from_label"]),
        "to_label": str(row["to_label"]),
        "from_x": row["from_china_x"] if scope == "china" else row["from_world_x"],
        "from_y": row["from_china_y"] if scope == "china" else row["from_world_y"],
        "to_x": row["to_china_x"] if scope == "china" else row["to_world_x"],
        "to_y": row["to_china_y"] if scope == "china" else row["to_world_y"],
        "from_precision": str(row["from_precision"]),
        "to_precision": str(row["to_precision"]),
        "amount": row["amount"],
        "currency": str(row["currency"]),
        "event_time": str(row["occurred_at"]),
        "source_name": str(row["source_name"]),
        "source_url": str(row["source_url"]),
        "source_license": str(row["source_license"]),
        "evidence_status": str(row["evidence_status"]),
        "captured_at": str(row["captured_at"]),
    }


def _external_payload(row: Any, scope: str = "global") -> dict[str, object]:
    map_x, map_y = (
        _china_xy_from_latlon(float(row["latitude"]), float(row["longitude"]))
        if scope == "china"
        else (float(row["world_x"]), float(row["world_y"]))
    )
    return {
        "id": str(row["id"]),
        "layer": "external",
        "source_event_id": str(row["source_event_id"]),
        "event_type": str(row["event_type"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "severity": str(row["severity"]),
        "magnitude": row["magnitude"],
        "region_name": str(row["region_name"]),
        "country_code": str(row["country_code"]),
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "map_x": map_x,
        "map_y": map_y,
        "coordinate_precision": str(row["coordinate_precision"]),
        "impact_radius_km": float(row["impact_radius_km"]),
        "event_time": str(row["event_time"]),
        "source_name": str(row["source_name"]),
        "source_url": str(row["source_url"]),
        "source_license": str(row["source_license"]),
        "access_policy": str(row["access_policy"]),
        "access_frequency": str(row["access_frequency"]),
        "evidence_status": str(row["evidence_status"]),
        "snapshot_sha256": str(row["snapshot_sha256"]),
        "captured_at": str(row["captured_at"]),
    }


def _impact_payload(row: Any) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "external_event_id": str(row["external_event_id"]),
        "target_type": str(row["target_type"]),
        "target_id": str(row["target_id"]),
        "target_title": str(row["target_title"]),
        "relation_basis": str(row["relation_basis"]),
        "rule_key": str(row["rule_key"]),
        "match_basis": _json_object(row["match_basis_json"]),
        "impact_scope": str(row["impact_scope"]),
        "severity": str(row["severity"]),
        "confidence": int(row["confidence"]),
        "explanation": str(row["explanation"]),
        "suggested_action": str(row["suggested_action"]),
        "review_status": str(row["review_status"]),
        "review_note": str(row["review_note"]),
        "reviewed_by": str(row["reviewed_by"] or ""),
        "reviewed_at": str(row["reviewed_at"] or ""),
    }


def _event_visible(
    item: dict[str, object],
    scope: str,
    cutoff: datetime | None,
    category: str,
) -> bool:
    if scope == "china" and item["country_code"] != "CN":
        return False
    if scope == "china" and (item["map_x"] is None or item["map_y"] is None):
        return False
    if category and item["category"] != category:
        return False
    return _time_visible(str(item["event_time"]), cutoff)


def _time_visible(value: str, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    parsed = _parse_time(value)
    return parsed is not None and parsed >= cutoff


def _clusters(
    geo_events: list[dict[str, object]],
    external_events: list[dict[str, object]],
) -> list[dict[str, object]]:
    buckets: dict[str, list[dict[str, object]]] = {}
    for item in geo_events + external_events:
        x = item.get("map_x")
        y = item.get("map_y")
        if x is None or y is None:
            continue
        key = f"{round(float(x) / 3) * 3:.0f}:{round(float(y) / 3) * 3:.0f}"
        buckets.setdefault(key, []).append(item)
    result = []
    for key, members in buckets.items():
        layers = Counter(str(item["layer"]) for item in members)
        result.append(
            {
                "id": key,
                "map_x": round(sum(float(item["map_x"]) for item in members) / len(members), 3),
                "map_y": round(sum(float(item["map_y"]) for item in members) / len(members), 3),
                "count": len(members),
                "primary_layer": layers.most_common(1)[0][0],
                "layers": dict(layers),
                "event_ids": [str(item["id"]) for item in members[:20]],
                "labels": [str(item["title"]) for item in members[:4]],
                "region_name": str(members[0].get("region_name") or ""),
            }
        )
    return sorted(result, key=lambda item: (-int(item["count"]), str(item["id"])))


def _timeline(
    geo_events: list[dict[str, object]], external_events: list[dict[str, object]]
) -> dict[str, object]:
    buckets: dict[str, Counter[str]] = {}
    for item in geo_events + external_events:
        parsed = _parse_time(str(item.get("event_time") or ""))
        if parsed is None:
            continue
        key = parsed.date().isoformat()
        buckets.setdefault(key, Counter())[str(item["layer"])] += 1
    frames = [
        {
            "time": key,
            "opportunity": counts.get("opportunity", 0),
            "award": counts.get("award", 0),
            "external": counts.get("external", 0),
            "total": sum(counts.values()),
        }
        for key, counts in sorted(buckets.items())
    ]
    if len(frames) > 90:
        frames = frames[-90:]
    return {
        "frames": frames,
        "start": frames[0]["time"] if frames else "",
        "end": frames[-1]["time"] if frames else "",
        "supports_pause": True,
        "supports_replay": True,
        "supports_comparison": True,
    }


def _impact_cards(
    external_events: list[dict[str, object]],
    impacts: list[dict[str, object]],
    geo_events: list[dict[str, object]],
    flows: list[dict[str, object]],
) -> list[dict[str, object]]:
    targets = {str(item["object_id"]): item for item in geo_events}
    flow_targets = {str(item["id"]): item for item in flows}
    result = []
    for event in external_events:
        links = [item for item in impacts if item["external_event_id"] == event["id"]]
        enriched = []
        for link in links:
            target = targets.get(str(link["target_id"])) or flow_targets.get(str(link["target_id"])) or {}
            enriched.append(
                {
                    **link,
                    "category": target.get("category", ""),
                    "region_name": target.get("region_name", ""),
                    "counterparty": target.get("counterparty", ""),
                    "notice_id": target.get("notice_id", ""),
                }
            )
        result.append({"event": event, "impacts": enriched, "impact_count": len(enriched)})
    return sorted(result, key=lambda item: (-int(item["impact_count"]), str(item["event"]["event_time"])), reverse=False)


def _impact_match(external: Any, target: Any) -> dict[str, object] | None:
    event_country = str(external["country_code"] or "")
    target_country = str(target["country_code"] or "")
    if event_country and event_country == target_country and event_country != "CN":
        return {
            "rule_key": "same-country-v1",
            "confidence": 86,
            "basis": {"event_country": event_country, "target_country": target_country, "kind": "same_country"},
            "explanation": "外部事件地点与项目地区被标准化为同一国家；这是规则关联，仍需核验实际交付地点和供应路径。",
        }
    if target["latitude"] is None or target["longitude"] is None:
        return None
    distance = _haversine(
        float(external["latitude"]),
        float(external["longitude"]),
        float(target["latitude"]),
        float(target["longitude"]),
    )
    if distance > float(external["impact_radius_km"]):
        return None
    return {
        "rule_key": "event-distance-v1",
        "confidence": 78,
        "basis": {
            "distance_km": round(distance, 1),
            "impact_radius_km": float(external["impact_radius_km"]),
            "kind": "distance",
        },
        "explanation": "项目区域中心落入事件候选半径；坐标精度可能仅到省或国家，必须人工确认实际地点。",
    }


def _flow_impact_match(external: Any, flow: Any) -> dict[str, object] | None:
    points = (
        (flow["from_latitude"], flow["from_longitude"], "from"),
        (flow["to_latitude"], flow["to_longitude"], "to"),
    )
    for latitude, longitude, endpoint in points:
        if latitude is None or longitude is None:
            continue
        distance = _haversine(
            float(external["latitude"]),
            float(external["longitude"]),
            float(latitude),
            float(longitude),
        )
        if distance <= float(external["impact_radius_km"]):
            return {
                "rule_key": "flow-endpoint-distance-v1",
                "confidence": 72,
                "basis": {"endpoint": endpoint, "distance_km": round(distance, 1)},
                "explanation": "交易流向的一端落入外部事件候选半径；这不证明实际运输路线经过事件区。",
            }
    return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    value = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _china_xy_from_latlon(latitude: float, longitude: float) -> tuple[float, float]:
    nearest = min(
        CHINA_CENTROIDS,
        key=lambda location_id: _haversine(
            latitude,
            longitude,
            CHINA_CENTROIDS[location_id][0],
            CHINA_CENTROIDS[location_id][1],
        ),
    )
    location = next(item for item in CHINA_LOCATIONS if item["id"] == nearest)
    return float(location["x"]), float(location["y"])


def _impact_severity(source: str) -> str:
    return {"critical": "high", "high": "high", "watch": "watch"}.get(source, "info")


def _category(title: str, content: str, fields: dict[str, object]) -> str:
    structured = fields.get("structured_fields") if isinstance(fields.get("structured_fields"), dict) else {}
    category = str(structured.get("category") or fields.get("category") or "").strip()
    if category:
        return category
    folded = f"{title} {content}".casefold()
    if re.search(r"\b(server|servers|data center|cloud computing)\b", folded):
        return "服务器"
    if re.search(r"\b(air conditioning|hvac|cooling system)\b", folded):
        return "空调"
    if re.search(r"\b(medical equipment|medical device)\b", folded):
        return "医疗设备"
    topic = extract_topic(f"{title} {content}")
    core = topic.get("core") if isinstance(topic.get("core"), list) else []
    return str(core[0]) if topic.get("origin") == "category_dict" and core else "其他"


def _is_award(content: str, fields: dict[str, object]) -> bool:
    raw = fields.get("raw") if isinstance(fields.get("raw"), dict) else {}
    information_type = str(raw.get("informationTypeText") or fields.get("information_type") or "")
    return any(token in f"{information_type} {content}" for token in ("中标", "成交", "采购合同", "award"))


def _supplier_name(content: str) -> str:
    match = re.search(
        r"(?:中标(?:（成交）)?|成交)供应商名称\s*(.{4,80}?)(?=\s*(?:合同金额|中标金额|成交金额|供应商地址|$))",
        content,
    )
    return match.group(1).strip() if match else ""


def _amount(content: str) -> tuple[float | None, str]:
    match = re.search(r"(?:合同金额|中标金额|成交金额)\s*([\d,]+(?:\.\d+)?)\s*(万元|元|美元|欧元|CNY|USD|EUR)?", content)
    if not match:
        return None, ""
    value = float(match.group(1).replace(",", ""))
    unit = match.group(2) or "元"
    if unit == "万元":
        return value * 10000, "CNY"
    return value, {"元": "CNY", "美元": "USD", "欧元": "EUR"}.get(unit, unit)


def _parse_time(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _epoch_iso(value: object) -> str:
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return ""


def _counter_items(counter: Counter[str], limit: int = 24) -> list[dict[str, object]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def _json_object(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}

