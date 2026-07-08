from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from tendertrace.adapters.ccgp import Notice
from tendertrace.report.naming import safe_report_filename


def _set_run_font(run, *, size: float = 11, bold: bool | None = None, color: str | None = None) -> None:
    run.font.name = "Calibri"
    rpr = run._element.get_or_add_rPr()
    rpr.rFonts.set(qn("w:ascii"), "Calibri")
    rpr.rFonts.set(qn("w:hAnsi"), "Calibri")
    rpr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def _style_doc(doc: Document) -> None:
    section = doc.sections[0]
    for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, attr, Inches(1))
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    style.font.size = Pt(11)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing = 1.15
    for name, size, color in (("Heading 1", 16, "2E74B5"), ("Heading 2", 13, "2E74B5")):
        heading = doc.styles[name]
        heading.font.name = "Calibri"
        heading._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        heading.font.size = Pt(size)
        heading.font.bold = True
        heading.font.color.rgb = RGBColor.from_string(color)


def _set_cell_text(cell, text: str, *, bold: bool = False) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(text)
    _set_run_font(run, size=9, bold=bold)


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _add_label_value(doc: Document, label: str, value: str) -> None:
    paragraph = doc.add_paragraph()
    label_run = paragraph.add_run(f"{label}：")
    _set_run_font(label_run, bold=True)
    value_run = paragraph.add_run(value or "无")
    _set_run_font(value_run)


def _notice_from_dict(value: dict[str, Any]) -> Notice:
    from tendertrace.adapters.ccgp import Attachment

    return Notice(
        id=value["id"],
        source_site=value["source_site"],
        title=value["title"],
        publish_time=value["publish_time"],
        region=value["region"],
        purchaser=value.get("purchaser", ""),
        source_url=value["source_url"],
        content_text=value.get("content_text", ""),
        core_content=value.get("core_content", ""),
        attachments=[Attachment(**item) for item in value.get("attachments", [])],
        fields=value.get("fields", {}),
    )


def _source_display(notice: Notice) -> str:
    value = notice.fields.get("source_sites")
    if isinstance(value, list) and value:
        return "、".join(str(item) for item in value)
    return notice.source_site


def _evidence(notice: Notice) -> dict[str, Any]:
    value = notice.fields.get("evidence")
    return value if isinstance(value, dict) else {}


def _evidence_status_text(notice: Notice) -> str:
    evidence = _evidence(notice)
    status = str(evidence.get("status") or notice.fields.get("evidence_status") or "未校验")
    score = evidence.get("quality_score", notice.fields.get("evidence_score"))
    if score is None:
        return status
    return f"{status}（score: {score}）"


def _attachment_parse_summary(notice: Notice) -> str:
    evidence = _evidence(notice)
    attachments = evidence.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return "无附件快照"
    extracted = sum(
        1
        for item in attachments
        if isinstance(item, dict) and str(item.get("status") or "") == "extracted"
    )
    downloaded = sum(
        1
        for item in attachments
        if isinstance(item, dict) and str(item.get("status") or "") in {"downloaded", "extracted"}
    )
    failed = sum(
        1
        for item in attachments
        if isinstance(item, dict) and str(item.get("status") or "") == "failed"
    )
    skipped = sum(
        1
        for item in attachments
        if isinstance(item, dict) and str(item.get("status") or "") == "skipped"
    )
    return f"已下载 {downloaded}/{len(attachments)}，已抽取正文 {extracted}，失败 {failed}，跳过 {skipped}"


def _attachment_excerpts(notice: Notice) -> list[str]:
    evidence = _evidence(notice)
    attachments = evidence.get("attachments")
    if not isinstance(attachments, list):
        return []
    excerpts: list[str] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        excerpt = str(item.get("text_excerpt") or "").strip()
        if not excerpt:
            continue
        name = str(item.get("name") or item.get("url") or "附件")
        excerpts.append(f"{name}：{excerpt[:360]}")
    return excerpts


def _region_scope(bidql: dict[str, Any]) -> dict[str, Any]:
    meta = bidql.get("meta")
    if not isinstance(meta, dict):
        return {}
    value = meta.get("region_scope")
    return value if isinstance(value, dict) else {}


def _region_display(bidql: dict[str, Any]) -> str:
    region = bidql.get("region")
    if not isinstance(region, dict):
        return "未限定"
    province = str(region.get("province") or "").strip()
    city = str(region.get("city") or "").strip()
    scope = _region_scope(bidql)
    if scope.get("status") == "relaxed_city" and city and province:
        return f"{city}（城市级无结果，已扩大至{province}省内）"
    if city and province:
        return f"{city}（{province}）"
    return province or "未限定"


def _region_scope_message(bidql: dict[str, Any]) -> str:
    scope = _region_scope(bidql)
    if scope.get("status") != "relaxed_city":
        return ""
    return str(scope.get("message") or "").strip()


def write_report(
    *,
    query: str,
    bidql: dict[str, Any],
    notices: list[Notice] | list[dict[str, Any]],
    output_dir: Path,
    generated_at: datetime,
    run_mode: str = "full",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized = [item if isinstance(item, Notice) else _notice_from_dict(item) for item in notices]
    path = output_dir / safe_report_filename(query, generated_at)

    doc = Document()
    _style_doc(doc)
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = title.add_run("TenderTrace 招投标信息汇总报告")
    _set_run_font(run, size=20, bold=True, color="000000")
    _add_label_value(doc, "用户问题", query)
    _add_label_value(doc, "生成时间", generated_at.strftime("%Y-%m-%d %H:%M"))
    _add_label_value(doc, "运行模式", run_mode)
    _add_label_value(doc, "关键词", "、".join(bidql.get("topic", {}).get("core", [])))
    _add_label_value(doc, "地区", _region_display(bidql))
    window = bidql.get("time", {}).get("resolved_window")
    if window:
        _add_label_value(doc, "时间窗口", f"{window['from']} 至 {window['to']}")
    region_note = _region_scope_message(bidql)
    if region_note:
        _add_label_value(doc, "地域范围说明", region_note)

    doc.add_heading("执行摘要", level=1)
    source_sites = sorted(
        {
            site
            for notice in normalized
            for site in (
                notice.fields.get("source_sites")
                if isinstance(notice.fields.get("source_sites"), list)
                else [notice.source_site]
            )
        }
    )
    source_text = "、".join(source_sites) if source_sites else "已配置来源"
    doc.add_paragraph(f"本次从 {source_text} 筛选出 {len(normalized)} 条符合条件的招投标信息。")
    if region_note:
        doc.add_paragraph(region_note)
    if not normalized:
        doc.add_paragraph("本轮未发现符合条件的新增招投标信息。")
        doc.save(path)
        return path

    doc.add_heading("结果总览", level=1)
    table = doc.add_table(rows=1, cols=6)
    table.style = "Table Grid"
    headers = ["序号", "标题", "发布时间", "来源", "地区", "附件数"]
    for cell, header in zip(table.rows[0].cells, headers, strict=True):
        _set_cell_text(cell, header, bold=True)
        _shade(cell, "E8EEF5")
    for index, notice in enumerate(normalized, start=1):
        row = table.add_row().cells
        values = [
            str(index),
            notice.title,
            notice.publish_time,
            _source_display(notice),
            notice.region,
            str(len(notice.attachments)),
        ]
        for cell, value in zip(row, values, strict=True):
            _set_cell_text(cell, value)

    doc.add_heading("逐条详情", level=1)
    for index, notice in enumerate(normalized, start=1):
        doc.add_heading(f"{index}. {notice.title}", level=2)
        _add_label_value(doc, "标题", notice.title)
        _add_label_value(doc, "发布时间", notice.publish_time)
        _add_label_value(doc, "来源链接", notice.source_url)
        _add_label_value(doc, "采购人", notice.purchaser)
        _add_label_value(doc, "核心内容", notice.core_content)
        evidence = _evidence(notice)
        if evidence:
            _add_label_value(doc, "事实校验", _evidence_status_text(notice))
            _add_label_value(doc, "证据哈希", str(evidence.get("snapshot_sha256") or "无"))
            _add_label_value(doc, "证据摘录", str(evidence.get("excerpt") or "无"))
            _add_label_value(doc, "附件解析", _attachment_parse_summary(notice))
        if int(notice.fields.get("duplicate_count") or 1) > 1:
            _add_label_value(doc, "关联来源", _source_display(notice))
        if notice.attachments:
            doc.add_paragraph("附件链接：")
            for attachment in notice.attachments:
                p = doc.add_paragraph(style="List Bullet")
                run = p.add_run(f"{attachment.name} - {attachment.url}")
                _set_run_font(run)
            excerpts = _attachment_excerpts(notice)
            if excerpts:
                doc.add_paragraph("附件正文摘录：")
                for excerpt in excerpts:
                    p = doc.add_paragraph(style="List Bullet")
                    run = p.add_run(excerpt)
                    _set_run_font(run)
        else:
            _add_label_value(doc, "附件链接", "无")

    doc.add_heading("附录", level=1)
    doc.add_paragraph("去重说明：本报告按来源站点、公告 ID、规范化 URL 和 cluster_key 去重；订阅增量另由 sent_history 控制。")
    doc.add_paragraph(
        "证据说明：来源链接指向对应公告详情页；核心内容由详情页正文抽取，不做生成式改写；"
        "事实校验基于标题、详情正文、核心内容和附件链接的可追溯证据生成。"
    )
    doc.save(path)
    return path
