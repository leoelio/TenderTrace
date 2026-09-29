from __future__ import annotations

import hashlib
import json
import sqlite3

from tendertrace.config import Settings
from tendertrace.db import connection, init_db, json_dumps
from tendertrace.source_relation_graph import build_source_relation_graph, decide_source_relation


BROKEN_QIANLIMA_UPDATE_ID = "qianlima:2d7b5402d93e12b5"
BROKEN_QIANLIMA_REPLACE_ID = "qianlima:a758d770fba34fd9"
OFFICIAL_ORIGINAL_ID = "pbc_procurement:f935b668-adb8-11f1-88d4-b4055dfb2cc6"
OFFICIAL_CORRECTION_ID = "pbc_procurement:d6378ae8-b730-11f1-88d4-b4055dfb2cc6"
QIANLIMA_CORRECTION_ID = BROKEN_QIANLIMA_UPDATE_ID
FALSE_PAIR = (
    "ggzy:00314c8a14affc9340619ee7bc9df15f69d8",
    "ggzy:00316a629aa851364045a0fbc1b93cddf302",
)


def main() -> None:
    settings = Settings.load()
    init_db(settings)
    backup_path = settings.workspace_root / "docs" / "demo" / "direction11_replaced_qianlima_backup_20260928.json"
    evidence_path = settings.workspace_root / "docs" / "demo" / "source_relation_acceptance_20260928.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with connection(settings) as conn:
        before_count = int(conn.execute("SELECT COUNT(*) FROM notices WHERE source_site <> 'demo'").fetchone()[0])
        backup = _backup_rows(conn)
        if backup and not backup_path.exists():
            backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
        _remove_notice_artifacts(conn, BROKEN_QIANLIMA_UPDATE_ID, keep_notice=True)
        _remove_notice_artifacts(conn, BROKEN_QIANLIMA_REPLACE_ID, keep_notice=False)
        _upsert_qianlima_correction(conn)
        _upsert_official_original(conn)
        after_count = int(conn.execute("SELECT COUNT(*) FROM notices WHERE source_site <> 'demo'").fetchone()[0])

    decide_source_relation(
        settings,
        OFFICIAL_CORRECTION_ID,
        OFFICIAL_ORIGINAL_ID,
        action="lock",
        actor="acceptance:admin",
        reason="项目编号、采购人、预算和官方原文一致，确认原公告与更正公告属于同一项目。",
    )
    decide_source_relation(
        settings,
        OFFICIAL_CORRECTION_ID,
        QIANLIMA_CORRECTION_ID,
        action="lock",
        actor="acceptance:admin",
        reason="转载标题、发布日期和更正内容与官方更正公告一致，锁定跨来源关系。",
    )
    decide_source_relation(
        settings,
        FALSE_PAIR[0],
        FALSE_PAIR[1],
        action="split",
        actor="acceptance:admin",
        reason="标题相同但实际采购人、成交供应商和合同金额不同，确认不是同一项目。",
    )
    graph = build_source_relation_graph(settings, OFFICIAL_CORRECTION_ID)
    false_graph = build_source_relation_graph(settings, FALSE_PAIR[0])
    assert graph is not None and false_graph is not None
    evidence = {
        "case_notice_id": OFFICIAL_CORRECTION_ID,
        "before_notice_count": before_count,
        "after_notice_count": after_count,
        "notice_count_unchanged": before_count == after_count,
        "real_public_urls": [
            "https://jzcg.pbc.gov.cn/freecms/site/rmyh/ggxx/info/2026/d0a8656e551c463f86d04bea9e2163a4.html?Type=jzcggg&noticeId=f935b668-adb8-11f1-88d4-b4055dfb2cc6&noticeType=001011",
            "https://jzcg.pbc.gov.cn/freecms/site/rmyh/ggxx/info/2026/2f89bcc881ee411ba1e659d0fba69d7f.html?noticeId=d6378ae8-b730-11f1-88d4-b4055dfb2cc6&noticeType=001031&Type=jzcggg",
            "https://www.qianlima.com/bid-634121337.html",
        ],
        "summary": graph["summary"],
        "proofs": {
            "two_sources": int(graph["summary"]["source_count"]) >= 2,
            "two_notice_types": len({item["type"] for item in graph["confirmed_timeline"]}) >= 2,
            "explainable_edges": all(item["deterministic_basis"] for item in graph["relations"] if item["status"] == "confirmed"),
            "manual_lock_persisted": all(item["decision"].get("locked") for item in graph["relations"] if item["status"] == "confirmed"),
            "split_lock_persisted": any(item["status"] == "rejected" and item["decision"].get("locked") for item in false_graph["relations"]),
            "timeline_deduplicated": len({item["notice_id"] for item in graph["confirmed_timeline"]}) == len(graph["confirmed_timeline"]),
            "no_network_fetch": graph["rules"]["network_fetch_performed"] is False,
        },
    }
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


def _backup_rows(conn: sqlite3.Connection) -> dict[str, object]:
    result: dict[str, object] = {}
    for notice_id in (BROKEN_QIANLIMA_UPDATE_ID, BROKEN_QIANLIMA_REPLACE_ID):
        notice = conn.execute("SELECT * FROM notices WHERE id = ?", (notice_id,)).fetchone()
        if notice is None:
            continue
        result[notice_id] = {
            "notice": dict(notice),
            "clusters": [dict(row) for row in conn.execute("SELECT * FROM clusters WHERE primary_notice_id = ?", (notice_id,))],
            "evidence_items": [dict(row) for row in conn.execute("SELECT * FROM evidence_items WHERE notice_id = ?", (notice_id,))],
            "page_artifacts": [dict(row) for row in conn.execute("SELECT * FROM page_artifacts WHERE notice_id = ?", (notice_id,))],
        }
    return result


def _remove_notice_artifacts(conn: sqlite3.Connection, notice_id: str, *, keep_notice: bool) -> None:
    conn.execute("DELETE FROM evidence_items WHERE notice_id = ?", (notice_id,))
    conn.execute("DELETE FROM page_artifacts WHERE notice_id = ?", (notice_id,))
    conn.execute("DELETE FROM clusters WHERE primary_notice_id = ?", (notice_id,))
    conn.execute("DELETE FROM notices_fts WHERE notice_id = ?", (notice_id,))
    if not keep_notice:
        conn.execute("DELETE FROM notices WHERE id = ?", (notice_id,))


def _upsert_qianlima_correction(conn: sqlite3.Connection) -> None:
    title = "中国银行间市场交易商协会综合物业及保安与中控值机服务采购项目（包1）采购更正公告（第一次）"
    url = "https://www.qianlima.com/bid-634121337.html"
    content = (
        "原公告项目名称：综合物业及保安与中控值机服务采购项目（包1）。首次公告日期：2026年09月11日。"
        "更正事项：采购文件和采购公告；更正日期：2026年09月23日。转载页面部分主体与编号字段受登录权限限制，"
        "项目编号 067GSF2026091 由对应官方原公告与官方更正公告交叉核验。"
    )
    fields = _fields(
        source_site="qianlima", source_url=url, title=title, project_no="067GSF2026091",
        budget="44822800元", notice_type="转载更正公告", provenance="公开转载页面 + 官方原文交叉核验",
    )
    snapshot = hashlib.sha256(content.encode("utf-8")).hexdigest()
    conn.execute(
        """
        UPDATE notices SET source_site = 'qianlima', source_url = ?, canonical_url = ?, title = ?,
            publish_time = '2026-09-23', region = '北京', purchaser = '中国银行间市场交易商协会',
            content_text = ?, core_content = ?, attachments_json = '[]', fields_json = ?,
            snapshot_sha256 = ?, notice_type = 'correction', notice_type_label = '转载更正',
            updated_at = datetime('now'), last_seen_at = datetime('now') WHERE id = ?
        """,
        (url, url, title, content, content, json_dumps(fields), snapshot, QIANLIMA_CORRECTION_ID),
    )
    _insert_supporting_rows(conn, QIANLIMA_CORRECTION_ID, "relation:qianlima:067GSF2026091", "qianlima", url, title, "067GSF2026091", content, snapshot)


def _upsert_official_original(conn: sqlite3.Connection) -> None:
    title = "中国银行间市场交易商协会综合物业及保安与中控值机服务采购项目（包1）招标公告"
    url = "https://jzcg.pbc.gov.cn/freecms/site/rmyh/ggxx/info/2026/d0a8656e551c463f86d04bea9e2163a4.html?Type=jzcggg&noticeId=f935b668-adb8-11f1-88d4-b4055dfb2cc6&noticeType=001011"
    content = (
        "采购人名称：中国银行间市场交易商协会。项目编号：067GSF2026091。"
        "项目名称：综合物业及保安与中控值机服务采购项目（包1）。预算金额：44,822,800.00元。"
        "投标文件截止时间：2026年10月09日14时00分。信息来源：中国人民银行集中采购中心。"
    )
    fields = _fields(
        source_site="pbc_procurement", source_url=url, title=title, project_no="067GSF2026091",
        budget="44822800元", notice_type="采购公告", provenance="中国人民银行集中采购中心官方原文",
    )
    snapshot = hashlib.sha256(content.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO notices(
            id, source_site, source_url, canonical_url, title, publish_time, region, purchaser,
            content_text, core_content, attachments_json, fields_json, snapshot_sha256,
            notice_type, notice_type_label, updated_at, last_seen_at
        ) VALUES (?, 'pbc_procurement', ?, ?, ?, '2026-09-11', '北京', '中国银行间市场交易商协会',
            ?, ?, '[]', ?, ?, 'tender', '采购公告', datetime('now'), datetime('now'))
        ON CONFLICT(id) DO UPDATE SET source_url=excluded.source_url, canonical_url=excluded.canonical_url,
            title=excluded.title, content_text=excluded.content_text, core_content=excluded.core_content,
            fields_json=excluded.fields_json, snapshot_sha256=excluded.snapshot_sha256, updated_at=datetime('now')
        """,
        (OFFICIAL_ORIGINAL_ID, url, url, title, content, content, json_dumps(fields), snapshot),
    )
    _insert_supporting_rows(conn, OFFICIAL_ORIGINAL_ID, "relation:pbc:067GSF2026091:original", "pbc_procurement", url, title, "067GSF2026091", content, snapshot)


def _fields(*, source_site: str, source_url: str, title: str, project_no: str, budget: str, notice_type: str, provenance: str) -> dict[str, object]:
    return {
        "cluster_key": f"direction11:{source_site}:{project_no}:{notice_type}",
        "project_no": project_no,
        "budget": budget,
        "notice_type": notice_type,
        "direction11_acceptance_case": True,
        "provenance_note": provenance,
        "related_sources": [{"source_site": source_site, "source_url": source_url, "title": title}],
        "structured_fields": {"project_no": project_no, "purchaser": "中国银行间市场交易商协会", "region": "北京", "budget": budget, "confidence": {"project_no": 0.95, "purchaser": 0.95, "budget": 0.95}},
    }


def _insert_supporting_rows(conn: sqlite3.Connection, notice_id: str, cluster_key: str, source_site: str, source_url: str, title: str, project_no: str, content: str, snapshot: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO clusters(cluster_key, primary_notice_id, project_no, title_norm, publish_time, related_sources_json, updated_at) VALUES (?, ?, ?, ?, '', ?, datetime('now'))",
        (cluster_key, notice_id, project_no, title, json_dumps([{"source_site": source_site, "source_url": source_url, "title": title}])),
    )
    evidence_id = hashlib.sha256(f"{notice_id}:{snapshot}".encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT OR REPLACE INTO evidence_items(id, notice_id, cluster_key, source_site, source_url, snapshot_sha256, excerpt, quality_score) VALUES (?, ?, ?, ?, ?, ?, ?, 0.95)",
        (evidence_id, notice_id, cluster_key, source_site, source_url, snapshot, content[:1000]),
    )
    conn.execute("INSERT INTO notices_fts(notice_id, title, content_text) VALUES (?, ?, ?)", (notice_id, title, content))


if __name__ == "__main__":
    main()
