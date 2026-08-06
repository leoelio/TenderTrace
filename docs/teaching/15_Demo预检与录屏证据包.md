# 15 Demo 预检与录屏证据包

这一节讲 `demo-check` 的设计。它不是为了替代 Demo 视频，而是为了避免录屏时才发现证据不完整。

## 为什么需要 demo-check

赛题要求 Demo 视频覆盖“输入到输出”的完整工作流，并覆盖多个问题。单靠一份脚本还不够，因为脚本只能告诉你应该演示什么，不能证明当前工作区真的有这些证据。

`demo-check` 把录屏前检查变成机器可执行：

- 数据库里是否有多个 finished run。
- 是否有多个不同自然语言问题。
- `outputs/` 和 `outbox/` 是否有 Word 文件。
- 最新 run 是否有 trace 工具链。
- 是否有订阅和 `sent_history` 增量记录。
- 模型和来源状态是否可展示。
- 视频文件是否已经放到 `docs/demo/`。

## 为什么不重跑采集

预检命令不应该改变演示现场。它只读当前状态，不联网、不重新抓取、不调用模型。

这样做有两个好处：

1. 录屏前的证据稳定。
2. 不会因为网络或外部站点波动改变结果。

真正需要刷新数据时，应该显式运行：

```powershell
python -m tendertrace run-once "最近7天全国服务器招标信息都有哪些" --max-pages 1 --max-results 2
```

## 核心代码结构

`tendertrace/demo_check.py` 中有三个核心类型：

```python
@dataclass(frozen=True)
class DemoCheck:
    name: str
    status: str
    detail: str

@dataclass(frozen=True)
class DemoEvidenceReport:
    status: str
    generated_at: str
    checks: list[DemoCheck]
    evidence: dict[str, Any]
```

每个检查项只做一件事。最后只要存在 `fail`，整体就是 `fail`；如果只有 `warn`，整体仍然是 `pass`，但 warning 必须在交付审计中透明说明。

## 关键检查项

`finished_runs` 检查：

- 至少有一个 finished run。
- 至少有两个不同问题。

`word_outbox` 检查：

- `outputs/` 有 Word。
- `outbox/` 有 Word。
- 最新 run 的 `output_docx_path` 存在。
- Word 里能读到标题、发布时间、来源链接、核心内容。

`trace_flow` 检查：

- `intent.rule_parser`
- `adapter.multi.collect`
- `pipeline.clean_dedup`
- `pipeline.evidence_validate`
- `report.docx_writer`

这些工具名来自真实 trace，不是文档里手写。

`subscription_incremental` 检查：

- 至少有一个 active subscription。
- `sent_history` 至少有一条记录。

这证明定时任务和增量不重复不是纯文档声明。

## warning 的意义

P15 有两个 warning 是合理的：

- 千里马登录态缺失：这是人工免费会员登录动作。
- Demo 视频文件缺失：视频需要人工录制。

这两个 warning 不应该被隐藏。隐藏它们会让交付审计失真。

## CLI 输出与证据包

直接查看：

```powershell
python -m tendertrace demo-check
```

写入证据包：

```powershell
python -m tendertrace demo-check --out docs/demo/demo_evidence_latest.json
```

这份 JSON 可以作为录屏前的检查记录，也可以在交付前复核。

## 测试覆盖

`tests/test_demo_check.py` 做两类验证：

1. 完整 fixture：真实 SQLite 表、两个 finished run、Word、outbox、trace、订阅和 sent_history 都存在时，`demo-check` 通过。
2. 空 fixture：缺少核心证据时，`demo-check` 失败。

这能避免把 Demo 证据检查写成硬编码通过。
