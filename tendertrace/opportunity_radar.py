from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.intent.topic import extract_topic
from tendertrace.retrieval import parse_date
from tendertrace.source_map import build_source_map


VALID_SCOPES = {"all", "domestic", "international"}

CHINA_LOCATIONS: tuple[dict[str, object], ...] = (
    {"id": "beijing", "name": "北京", "aliases": ("北京", "北京市"), "x": 70, "y": 25},
    {"id": "tianjin", "name": "天津", "aliases": ("天津", "天津市"), "x": 74, "y": 28},
    {"id": "hebei", "name": "河北", "aliases": ("河北", "河北省"), "x": 68, "y": 31},
    {"id": "shanxi", "name": "山西", "aliases": ("山西", "山西省"), "x": 61, "y": 34},
    {"id": "inner-mongolia", "name": "内蒙古", "aliases": ("内蒙古", "内蒙古自治区"), "x": 59, "y": 22},
    {"id": "liaoning", "name": "辽宁", "aliases": ("辽宁", "辽宁省"), "x": 78, "y": 22},
    {"id": "jilin", "name": "吉林", "aliases": ("吉林", "吉林省"), "x": 82, "y": 17},
    {"id": "heilongjiang", "name": "黑龙江", "aliases": ("黑龙江", "黑龙江省"), "x": 83, "y": 10},
    {"id": "shanghai", "name": "上海", "aliases": ("上海", "上海市"), "x": 76, "y": 48},
    {"id": "jiangsu", "name": "江苏", "aliases": ("江苏", "江苏省"), "x": 72, "y": 45},
    {"id": "zhejiang", "name": "浙江", "aliases": ("浙江", "浙江省"), "x": 73, "y": 53},
    {"id": "anhui", "name": "安徽", "aliases": ("安徽", "安徽省", "蚌埠"), "x": 66, "y": 48},
    {"id": "fujian", "name": "福建", "aliases": ("福建", "福建省"), "x": 69, "y": 62},
    {"id": "jiangxi", "name": "江西", "aliases": ("江西", "江西省"), "x": 63, "y": 57},
    {"id": "shandong", "name": "山东", "aliases": ("山东", "山东省"), "x": 70, "y": 37},
    {"id": "henan", "name": "河南", "aliases": ("河南", "河南省"), "x": 60, "y": 43},
    {"id": "hubei", "name": "湖北", "aliases": ("湖北", "湖北省"), "x": 57, "y": 51},
    {"id": "hunan", "name": "湖南", "aliases": ("湖南", "湖南省"), "x": 55, "y": 60},
    {"id": "guangdong", "name": "广东", "aliases": ("广东", "广东省"), "x": 59, "y": 70},
    {"id": "guangxi", "name": "广西", "aliases": ("广西", "广西壮族自治区"), "x": 51, "y": 70},
    {"id": "hainan", "name": "海南", "aliases": ("海南", "海南省"), "x": 55, "y": 80},
    {"id": "chongqing", "name": "重庆", "aliases": ("重庆", "重庆市"), "x": 47, "y": 55},
    {"id": "sichuan", "name": "四川", "aliases": ("四川", "四川省"), "x": 39, "y": 52},
    {"id": "guizhou", "name": "贵州", "aliases": ("贵州", "贵州省"), "x": 45, "y": 64},
    {"id": "yunnan", "name": "云南", "aliases": ("云南", "云南省"), "x": 35, "y": 70},
    {"id": "tibet", "name": "西藏", "aliases": ("西藏", "西藏自治区"), "x": 21, "y": 54},
    {"id": "shaanxi", "name": "陕西", "aliases": ("陕西", "陕西省"), "x": 50, "y": 42},
    {"id": "gansu", "name": "甘肃", "aliases": ("甘肃", "甘肃省"), "x": 39, "y": 36},
    {"id": "qinghai", "name": "青海", "aliases": ("青海", "青海省"), "x": 30, "y": 40},
    {"id": "ningxia", "name": "宁夏", "aliases": ("宁夏", "宁夏回族自治区"), "x": 48, "y": 33},
    {"id": "xinjiang", "name": "新疆", "aliases": ("新疆", "新疆维吾尔自治区"), "x": 15, "y": 27},
    {"id": "hong-kong", "name": "香港", "aliases": ("香港", "香港特别行政区"), "x": 61, "y": 74},
    {"id": "macao", "name": "澳门", "aliases": ("澳门", "澳门特别行政区"), "x": 57, "y": 74},
    {"id": "taiwan", "name": "台湾", "aliases": ("台湾", "台湾省"), "x": 75, "y": 65},
)

WORLD_LOCATIONS: tuple[dict[str, object], ...] = (
    {"id": "china", "name": "中国", "aliases": ("全国", "China", "中国"), "x": 76, "y": 42},
    {"id": "europe", "name": "欧洲", "aliases": ("Europe", "European", "EU", "DEU", "NLD", "ROU", "UK", "UKC", "UKD", "United Kingdom"), "x": 51, "y": 30},
    {"id": "north-america", "name": "北美", "aliases": ("Canada", "Ontario", "United States", "USA", "North America"), "x": 20, "y": 31},
    {"id": "latin-america", "name": "拉丁美洲", "aliases": ("Uruguay", "Brazil", "Argentina", "Latin America", "Caribbean"), "x": 32, "y": 69},
    {"id": "africa", "name": "非洲", "aliases": ("Africa", "Mozambique", "Burundi", "Kenya", "Nigeria", "Egypt"), "x": 53, "y": 61},
    {"id": "central-asia", "name": "中亚与东欧", "aliases": ("Ukraine", "Kazakhstan", "Uzbekistan", "EBRD"), "x": 61, "y": 33},
    {"id": "south-asia", "name": "南亚", "aliases": ("India", "Pakistan", "Bangladesh", "Sri Lanka", "South Asia"), "x": 68, "y": 52},
    {"id": "southeast-asia", "name": "东南亚", "aliases": ("Philippines", "Indonesia", "Vietnam", "Thailand", "Malaysia", "Asia-Pacific", "ADB"), "x": 78, "y": 59},
    {"id": "middle-east", "name": "中东", "aliases": ("Middle East", "Saudi", "UAE", "Qatar", "Jordan"), "x": 59, "y": 48},
    {"id": "oceania", "name": "大洋洲", "aliases": ("Australia", "New Zealand", "Oceania"), "x": 86, "y": 75},
    {"id": "global", "name": "全球多地区", "aliases": ("Global", "Multiple Countries", "Worldwide"), "x": 47, "y": 46},
)

DOMESTIC_SOURCES = {"ccgp", "ggzy", "pbc_procurement", "zzcg", "qianlima"}
SOURCE_ANCHORS = {
    "ccgp": (76, 42), "ggzy": (76, 42), "pbc_procurement": (76, 42), "zzcg": (76, 42), "qianlima": (76, 42),
    "ted": (51, 30), "ungm": (47, 46), "worldbank": (47, 46), "idb": (32, 69), "adb": (78, 59),
    "afdb": (53, 61), "ebrd": (61, 33), "contracts_finder": (49, 27), "find_tender": (49, 27),
    "canadabuys": (20, 31), "prozorro": (61, 33),
}


def build_opportunity_radar(
    settings: Settings,
    *,
    scope: str = "all",
    window_days: int = 365,
    category: str = "",
    persist: bool = False,
    actor: str = "admin",
) -> dict[str, object]:
    """Build an explainable radar from the local notice index and source observations only."""
    init_db(settings)
    scope = _validate_scope(scope)
    window_days = max(0, min(int(window_days), 3650))
    category = " ".join(category.split())[:80]
    rows = _notice_rows(settings)
    source_map = build_source_map(settings)
    sources = _source_payloads(source_map, rows, scope=scope)
    indexed = [_notice_payload(row, source_map) for row in rows]
    filtered = [
        item for item in indexed
        if _in_scope(item, scope)
        and _in_window(str(item["publish_time"]), window_days)
        and (not category or item["category"] == category)
    ]
    locations = _aggregate_locations(filtered, scope)
    categories = _counter_payload(Counter(str(item["category"]) for item in filtered), limit=12)
    available_categories = _counter_payload(Counter(str(item["category"]) for item in indexed if _in_scope(item, scope)), limit=30)
    data_as_of = max((str(item["indexed_at"]) for item in filtered), default=_latest_index_time(rows))
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fresh_cutoff = date.today() - timedelta(days=7)
    recent_count = sum(bool(item["publish_date"] and item["publish_date"] >= fresh_cutoff.isoformat()) for item in filtered)
    healthy_count = sum(item["availability_status"] == "healthy" for item in sources)
    limited_count = sum(item["availability_status"] == "access_limited" for item in sources)
    fault_count = sum(item["availability_status"] in {"degraded", "fault"} for item in sources)
    payload: dict[str, object] = {
        "scope": scope,
        "window_days": window_days,
        "category": category,
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "index_mode": "local_index",
        "network_fetch_performed": False,
        "summary": {
            "opportunity_count": len(filtered),
            "recent_7d_count": recent_count,
            "location_count": sum(item["opportunity_count"] > 0 for item in locations),
            "source_count": len(sources),
            "healthy_source_count": healthy_count,
            "attention_source_count": fault_count,
            "limited_source_count": limited_count,
            "zero_result_source_count": sum(item["data_status"] == "zero_results" for item in sources),
        },
        "locations": locations,
        "categories": categories,
        "available_categories": available_categories,
        "sources": sources,
        "opportunities": sorted(filtered, key=lambda item: (str(item["publish_date"]), str(item["indexed_at"])), reverse=True)[:200],
        "latest": sorted(filtered, key=lambda item: (str(item["publish_date"]), str(item["indexed_at"])), reverse=True)[:12],
        "legend": {
            "opportunity_size": "圆点大小表示本地索引机会数量",
            "opportunity_color": "颜色表示该地区机会对应来源的平均可信度",
            "source_status": "来源可用状态与本地结果数量分别展示，0条结果不等于来源故障",
        },
        "rules": {
            "real_local_index_only": True,
            "random_points_forbidden": True,
            "zero_results_separate_from_faults": True,
            "offline_snapshot_supported": True,
            "manual_refresh_only": True,
        },
    }
    latest_snapshot = latest_opportunity_radar_snapshot(settings, scope=scope, window_days=window_days, category=category)
    payload["snapshot"] = latest_snapshot or {}
    if persist:
        payload["snapshot"] = _persist_snapshot(settings, payload, actor=actor)
    return payload


def latest_opportunity_radar_snapshot(settings: Settings, *, scope: str, window_days: int, category: str = "") -> dict[str, object] | None:
    scope = _validate_scope(scope)
    with connection(settings) as conn:
        row = conn.execute(
            """
            SELECT id, notice_count, source_count, created_by, created_at
            FROM opportunity_radar_snapshots
            WHERE scope = ? AND window_days = ? AND category = ?
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (scope, int(window_days), category),
        ).fetchone()
    if row is None:
        return None
    return {"id": str(row["id"]), "notice_count": int(row["notice_count"]), "source_count": int(row["source_count"]), "created_by": str(row["created_by"]), "created_at": str(row["created_at"])}


def _notice_rows(settings: Settings) -> list[Any]:
    with connection(settings) as conn:
        return conn.execute(
            """
            SELECT id, source_site, source_url, title, publish_time, region, purchaser,
                   content_text, core_content, fields_json, updated_at, last_seen_at
            FROM notices WHERE source_site <> '' AND source_site <> 'demo'
            ORDER BY COALESCE(publish_time, created_at) DESC, rowid DESC
            """
        ).fetchall()


def _notice_payload(row: Any, source_map: dict[str, object]) -> dict[str, object]:
    region = str(row["region"] or "").strip()
    location = _resolve_location(region, str(row["source_site"] or ""))
    fields = _json_object(row["fields_json"])
    structured = fields.get("structured_fields") if isinstance(fields.get("structured_fields"), dict) else {}
    category = str(structured.get("category") or fields.get("category") or "").strip()
    if not category:
        topic = extract_topic(" ".join((str(row["title"] or ""), str(row["core_content"] or row["content_text"] or ""))))
        core = topic.get("core") if isinstance(topic.get("core"), list) else []
        category = str(core[0]) if topic.get("origin") == "category_dict" and core else "其他"
    health = _source_health(source_map, str(row["source_site"] or ""))
    publish = parse_date(str(row["publish_time"] or ""))
    return {
        "notice_id": str(row["id"]), "title": str(row["title"]), "source_site": str(row["source_site"]),
        "source_url": str(row["source_url"]), "region": region or location["name"], "purchaser": str(row["purchaser"] or ""),
        "category": category, "publish_time": str(row["publish_time"] or ""), "publish_date": publish.isoformat() if publish else "",
        "indexed_at": str(row["last_seen_at"] or row["updated_at"] or ""), "location_id": location["id"],
        "location_name": location["name"], "domestic": location["domestic"], "china_x": location["china_x"], "china_y": location["china_y"],
        "world_x": location["world_x"], "world_y": location["world_y"], "source_reliability": float(health.get("reliability_score") or 0),
    }


def _aggregate_locations(items: list[dict[str, object]], scope: str) -> list[dict[str, object]]:
    buckets: dict[str, list[dict[str, object]]] = {}
    for item in items:
        buckets.setdefault(str(item["location_id"]), []).append(item)
    result: list[dict[str, object]] = []
    for location_id, members in buckets.items():
        first = members[0]
        categories = Counter(str(item["category"]) for item in members)
        sites = Counter(str(item["source_site"]) for item in members)
        reliability_values = [float(item["source_reliability"]) for item in members if float(item["source_reliability"]) > 0]
        reliability = round(sum(reliability_values) / len(reliability_values), 3) if reliability_values else 0.0
        result.append({
            "id": location_id, "name": first["location_name"], "domestic": first["domestic"],
            "china_x": first["china_x"], "china_y": first["china_y"], "world_x": first["world_x"], "world_y": first["world_y"],
            "opportunity_count": len(members), "recent_7d_count": sum(_is_recent(str(item["publish_date"]), 7) for item in members),
            "reliability_score": reliability, "reliability_status": _reliability_label(reliability),
            "hot_categories": _counter_payload(categories, limit=3), "source_sites": _counter_payload(sites, limit=5),
            "notice_ids": [str(item["notice_id"]) for item in sorted(members, key=lambda item: str(item["publish_date"]), reverse=True)[:12]],
        })
    return sorted(result, key=lambda item: (-int(item["opportunity_count"]), str(item["name"])))


def _source_payloads(source_map: dict[str, object], rows: list[Any], *, scope: str) -> list[dict[str, object]]:
    counts = Counter(str(row["source_site"] or "") for row in rows)
    result = []
    for raw in source_map.get("items", []):
        if not isinstance(raw, dict):
            continue
        site = str(raw.get("site") or "")
        domestic = site in DOMESTIC_SOURCES
        if scope == "domestic" and not domestic:
            continue
        if scope == "international" and domestic:
            continue
        health = raw.get("health") if isinstance(raw.get("health"), dict) else {}
        availability, availability_label = _source_availability(raw, health)
        local_count = int(counts.get(site, 0))
        rules = raw.get("discovery_rules") if isinstance(raw.get("discovery_rules"), dict) else {}
        anchor = SOURCE_ANCHORS.get(site, (47, 46))
        restrictions = []
        if raw.get("requires_login"):
            restrictions.append("需要登录")
        if rules.get("license"):
            restrictions.append(f"许可：{rules['license']}")
        if rules.get("coverage"):
            restrictions.append(str(rules["coverage"]))
        if health.get("last_error"):
            restrictions.append(_compact_error(str(health["last_error"])))
        result.append({
            "site": site, "authority": str(rules.get("authority") or site), "engine": str(raw.get("engine") or ""),
            "domestic": domestic, "world_x": anchor[0], "world_y": anchor[1], "configured_status": str(raw.get("status") or "unknown"),
            "availability_status": availability, "availability_label": availability_label,
            "data_status": "has_results" if local_count else "zero_results", "data_status_label": f"本地索引 {local_count} 条" if local_count else "本地索引 0 条",
            "local_notice_count": local_count, "runs": int(health.get("runs") or 0), "success_rate": health.get("success_rate"),
            "reliability_score": float(health.get("reliability_score") or 0), "avg_elapsed_ms": int(health.get("avg_elapsed_ms") or 0),
            "last_run_at": str(health.get("last_run_at") or ""), "last_success_at": str(health.get("last_success_at") or ""),
            "last_failure_at": str(health.get("last_failure_at") or ""), "last_error": _compact_error(str(health.get("last_error") or "")),
            "restrictions": restrictions[:3], "route_count": len(raw.get("routes") or []),
        })
    order = {"fault": 0, "access_limited": 1, "degraded": 2, "unverified": 3, "healthy": 4}
    return sorted(result, key=lambda item: (order.get(str(item["availability_status"]), 9), str(item["site"])))


def _source_availability(item: dict[str, object], health: dict[str, object]) -> tuple[str, str]:
    configured = str(item.get("status") or "")
    if configured in {"login_required", "login_expired"}:
        return "access_limited", "访问受限"
    runs = int(health.get("runs") or 0)
    if not runs:
        return "unverified", "尚未验证"
    status = str(health.get("health_status") or "unknown")
    last_success = str(health.get("last_success_at") or "")
    last_failure = str(health.get("last_failure_at") or "")
    if status == "unhealthy" or (last_failure and (not last_success or last_failure > last_success)):
        return "fault", "当前异常"
    if status == "degraded":
        return "degraded", "性能下降"
    if status == "healthy":
        return "healthy", "运行正常"
    return "unverified", "状态未知"


def _resolve_location(region: str, source_site: str) -> dict[str, object]:
    folded = region.casefold()
    for location in CHINA_LOCATIONS:
        if any(str(alias).casefold() in folded for alias in location["aliases"]):
            return {"id": location["id"], "name": location["name"], "domestic": True, "china_x": location["x"], "china_y": location["y"], "world_x": 76 + (float(location["x"]) - 50) * 0.12, "world_y": 42 + (float(location["y"]) - 48) * 0.08}
    if source_site in DOMESTIC_SOURCES or region in {"全国", "中国", ""}:
        return {"id": "china-national", "name": "全国", "domestic": True, "china_x": 50, "china_y": 48, "world_x": 76, "world_y": 42}
    for location in WORLD_LOCATIONS:
        if any(str(alias).casefold() in folded for alias in location["aliases"]):
            return {"id": location["id"], "name": location["name"], "domestic": False, "china_x": 50, "china_y": 48, "world_x": location["x"], "world_y": location["y"]}
    anchor = SOURCE_ANCHORS.get(source_site, (47, 46))
    return {"id": f"other-{_stable_key(region or source_site)}", "name": region or "地区待核", "domestic": False, "china_x": 50, "china_y": 48, "world_x": anchor[0], "world_y": anchor[1]}


def _persist_snapshot(settings: Settings, payload: dict[str, object], *, actor: str) -> dict[str, object]:
    signature = "|".join((str(payload["scope"]), str(payload["window_days"]), str(payload["category"]), str(payload["generated_at"])))
    snapshot_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]
    stored = {key: value for key, value in payload.items() if key != "snapshot"}
    with connection(settings) as conn:
        conn.execute(
            "INSERT INTO opportunity_radar_snapshots(id, scope, window_days, category, notice_count, source_count, payload_json, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, payload["scope"], payload["window_days"], payload["category"], payload["summary"]["opportunity_count"], payload["summary"]["source_count"], json_dumps(stored), actor.strip() or "admin"),
        )
        row = conn.execute("SELECT created_at FROM opportunity_radar_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    return {"id": snapshot_id, "notice_count": payload["summary"]["opportunity_count"], "source_count": payload["summary"]["source_count"], "created_by": actor.strip() or "admin", "created_at": str(row["created_at"] if row else "")}


def _validate_scope(scope: str) -> str:
    value = str(scope or "all").strip().lower()
    if value not in VALID_SCOPES:
        raise ValueError("scope must be all, domestic or international")
    return value


def _in_scope(item: dict[str, object], scope: str) -> bool:
    return scope == "all" or (scope == "domestic" and bool(item["domestic"])) or (scope == "international" and not bool(item["domestic"]))


def _in_window(value: str, days: int) -> bool:
    if days == 0:
        return True
    parsed = parse_date(value)
    return bool(parsed and parsed >= date.today() - timedelta(days=days))


def _is_recent(value: str, days: int) -> bool:
    parsed = parse_date(value)
    return bool(parsed and parsed >= date.today() - timedelta(days=days))


def _counter_payload(counter: Counter[str], *, limit: int) -> list[dict[str, object]]:
    return [{"name": key or "其他", "count": int(value)} for key, value in counter.most_common(limit)]


def _source_health(source_map: dict[str, object], site: str) -> dict[str, object]:
    for item in source_map.get("items", []):
        if isinstance(item, dict) and item.get("site") == site:
            return item.get("health") if isinstance(item.get("health"), dict) else {}
    return {}


def _latest_index_time(rows: list[Any]) -> str:
    return max((str(row["last_seen_at"] or row["updated_at"] or "") for row in rows), default="")


def _reliability_label(score: float) -> str:
    return "可信" if score >= 0.85 else "需关注" if score >= 0.6 else "待验证"


def _compact_error(value: str) -> str:
    return " ".join(value.split())[:180]


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
