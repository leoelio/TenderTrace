# 03 HTTP 公开源适配器与首份报告

## 本阶段解决什么问题

P3 让系统第一次从真实互联网来源拿到招投标信息，并生成赛题要求的 Word 文件。

这一步有三个关键目标：

1. 采集器不能硬编码结果，必须从网页列表和详情页抽取。
2. 报告必须可交付，字段覆盖标题、发布时间、来源链接、核心内容和附件链接。
3. 运行必须可追踪，后续 UI 和定时任务能根据 `run_id` 查到文件、事件和检查点。

## 源码地图

- `tendertrace/adapters/ccgp.py`：公开源 HTTP 采集器。
- `tendertrace/report/naming.py`：生成安全文件名。
- `tendertrace/report/docx_writer.py`：写 Word 报告。
- `tendertrace/runlog.py`：写运行台账和 outbox 台账。
- `tendertrace/cli.py`：把意图解析、采集和报告串成一次图运行。
- `tests/test_ccgp_adapter.py`：列表页、详情页和附件解析测试。
- `tests/test_report_writer.py`：Word 报告结构测试。
- `tests/test_runlog.py`：运行台账测试。
- `tests/test_api_outbox.py`：outbox API 可追踪性测试。

## 采集器数据结构

`Notice` 是本阶段的核心数据对象：

```python
@dataclass(frozen=True)
class Notice:
    id: str
    source_site: str
    title: str
    publish_time: str
    region: str
    purchaser: str
    source_url: str
    content_text: str = ""
    core_content: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    fields: dict[str, Any] = field(default_factory=dict)
```

这里用 `frozen=True` 是为了让采集结果不可变。详情页增强时，不在原对象上原地修改，而是返回一个新的 `Notice`。这样图运行里的状态更容易追踪，也避免后续节点意外改掉上游数据。

## 列表页解析

`parse_list_page()` 只做一件事：从列表 HTML 中抽取公告元数据。

```python
for item in parser.css("ul.c_list_bid li"):
    anchor = item.css_first("a")
    if anchor is None:
        continue
    title = _clean_spaces(anchor.text())
    source_url = urljoin(page_url, anchor.attributes.get("href", ""))
```

这里没有用字符串切片，而是用 `selectolax` 按 CSS 选择器解析。原因是列表项里通常混合了链接、发布时间、地域和采购人，DOM 解析比正则直接扫整页可靠。

后面这段正则只处理单个列表项的文本：

```python
match = re.search(
    r"发布时间：\s*(?P<time>.*?)\s*地域：\s*(?P<region>.*?)\s*采购人：\s*(?P<purchaser>.*)$",
    text,
)
```

正则范围越小，风险越低。它不是在解析整个网页结构，只是在已经定位到的 `li` 内抽字段。

## 详情页增强

详情页增强由 `enrich_from_detail()` 完成：

```python
content = _extract_content(parser)
return Notice(
    id=notice.id,
    source_site=notice.source_site,
    title=notice.title,
    publish_time=notice.publish_time,
    region=notice.region,
    purchaser=notice.purchaser,
    source_url=notice.source_url,
    content_text=content,
    core_content=_summarize(content),
    attachments=_extract_attachments(parser, notice.source_url),
)
```

正文优先从 `#noticeArea` 抽取，这是中国政府采购网详情页常见正文容器。抽取前会移除 `script` 和 `style`，避免把页面脚本写进报告。

附件提取看两类信号：

- 链接后缀是 `.pdf`、`.doc`、`.docx`、`.xls`、`.xlsx`、`.zip`、`.rar`。
- 链接文本包含“附件”。

这不是最终附件策略，但足够覆盖 P3 的公开源首版闭环。

## BidQL 过滤

采集器会用 BidQL 做三类过滤：

- 地区：匹配省份或别名。
- 时间：发布时间落在 `resolved_window` 内。
- 主题：标题、地区、采购人或正文中包含核心词/扩展词。

当前过滤逻辑故意保持简单，因为 P3 的目标是跑通真实链路。跨源去重、相似标题归并和语义相关性会在后续阶段扩展。

## Word 文件名

赛题要求文件名形如：

```text
{用户的问题}_{时间}.docx
```

`safe_report_filename()` 做两件事：

1. 替换 Windows 文件名非法字符。
2. 文件名太长时保留前缀并追加短 hash。

```python
clean = _ILLEGAL.sub("_", query).strip(" ._") or "招投标信息汇总"
stamp = now.strftime("%Y%m%d%H%M")
suffix = f"_{stamp}.docx"
```

这样既满足赛题命名，又不会因为用户输入里带 `/`、`:`、换行等字符导致写文件失败。

## Word 报告生成

`write_report()` 使用 `python-docx` 写结构化报告。它不把网页全文直接堆进去，而是分成：

- 报告元信息
- 执行摘要
- 结果总览表
- 逐条详情
- 附录

逐条详情里明确写：

```python
_add_label_value(doc, "标题", notice.title)
_add_label_value(doc, "发布时间", notice.publish_time)
_add_label_value(doc, "来源链接", notice.source_url)
_add_label_value(doc, "采购人", notice.purchaser)
_add_label_value(doc, "核心内容", notice.core_content)
```

这些字段对应赛题的硬性输出要求。附件为空时写“无”，避免报告读者误以为空白是生成失败。

## 运行台账

`runlog.py` 把一次运行拆成两个层次：

- `runs`：一次任务的整体状态。
- `outbox_messages`：一个可下载 Word 文件。

这两个表通过 `run_id` 关联。UI 阶段可以先展示 outbox 文件，再用 `run_id` 拉取 trace 和 checkpoint。

```python
register_outbox_message(settings, run_id=state.run_id, docx_path=outbox_path)
```

这行代码看起来很小，但它让“文件可下载”变成“文件可解释”：用户可以知道这个文件来自哪次运行、运行了哪些节点、采集到了多少条数据。

## CLI 如何串起来

`run-once` 内部仍然使用 P1 的 TenderGraph：

```text
intent -> collect -> report
```

每个节点只做自己的事情：

- `intent`：把自然语言编译成 BidQL。
- `collect`：调用公开源适配器，返回 Notice 列表。
- `report`：生成 Word，复制到 outbox，登记 outbox 消息。

这种拆法的价值是后续容易替换某个节点。例如 P4 可以增加 Web UI 调用同一条图，P5 可以把 `collect` 扩展成多源并发采集。

## 验证方法

本阶段的测试覆盖四个层次：

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
python -m tendertrace run-once "最近36个月的上海区域内的设备招标信息都有哪些" --now "2026-07-06T10:00:00+08:00" --max-pages 2 --max-results 3
```

重点看：

- `parse_list_page()` 是否能从列表页抽标题、发布时间、地域、采购人和详情链接。
- `enrich_from_detail()` 是否能抽正文、清理脚本、识别附件。
- `write_report()` 生成的 DOCX 是否能被 `python-docx` 读回，并包含必需字段。
- `runlog` 是否把同一个 `run_id` 写入 `runs` 和 `outbox_messages`。
- 真实 `run-once` 是否生成 `outputs` 与 `outbox` 两份 Word。

## 下一阶段如何接上

P4 适合做 Web UI 工作台：

- 输入自然语言问题。
- 触发 `run-once`。
- 展示 outbox 文件列表。
- 点击下载 Word。
- 点击 run_id 查看 trace 和 checkpoint。

P5 再接入定时任务和 `sent_history` 增量控制。这样先把立即运行链路做稳，再把它放进调度器里重复执行。
