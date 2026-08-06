# TenderTrace Demo 演示脚本

## 1. 演示目标

Demo 视频需要覆盖从输入到输出的完整工作流，并覆盖多个问题。建议录制 6 到 8 分钟，重点展示系统不是硬编码结果，而是有真实事件流、来源状态、模型状态、Word 输出和增量账本。

## 2. 录制前准备

```powershell
cd D:\超聚变
python -m tendertrace config-check
python -m tendertrace model-status
python -m tendertrace model-doctor
python -m tendertrace source-status
python -m tendertrace verify-qianlima
python -m tendertrace acceptance-check
python -m tendertrace demo-check --out docs/demo/demo_evidence_latest.json
python -m tendertrace demo-video --url http://127.0.0.1:8000/ --out docs/demo/TenderTrace_Demo.mp4
python -m tendertrace package-submission
python -m unittest discover -s tests -v
python -m ruff check .
```

启动服务：

```powershell
python -m tendertrace serve
```

打开：

```text
http://127.0.0.1:8000/
```

如果端口占用，使用 8001：

```powershell
$env:TENDERTRACE_PORT='8001'
python -m tendertrace serve
```

## 3. 镜头一：系统状态

展示 Web 顶部和状态面板：

- API 已连接。
- 来源状态包含 `ccgp`、`ggzy`、`qianlima`。
- Model 面板显示 cloud/openai 或 local/ollama。
- Outbox 表格可追踪历史 Word。

讲解要点：

- 系统支持公开源和登录态来源。
- key 不在 UI 中展示。
- 模型只是增强通道，失败时规则流程仍可运行。

## 4. 镜头二：立即执行问题

输入：

```text
最近7天全国服务器招标信息都有哪些
```

参数：

```text
max_pages=1
max_results=2
```

点击运行采集。

等待运行完成后展示：

- Run ID。
- 结果数。
- Trace 数量。
- 证据通过数。
- 附件正文数量。
- 最新 Word 下载条。

点击“追踪”，展示事件流：

- `intent.rule_parser`
- `llm.intent_enhancer`
- `adapter.*.collect`
- `pipeline.clean_dedup`
- `pipeline.evidence_validate`
- `report.docx_writer`

打开 Word，展示：

- 文件名符合规则。
- 检索条件。
- 来源统计。
- 公告标题。
- 发布时间。
- 来源链接。
- 核心内容。
- 附件链接。
- 证据摘录。

## 5. 镜头三：另一个问题

输入：

```text
2026年3月份上海区域内的充电桩招标信息都有哪些
```

展示意图解析或运行结果，强调：

- 系统能识别绝对月份。
- 时间窗口不是固定写死。
- 不同主题会生成不同搜索词。

## 6. 镜头四：创建订阅

输入：

```text
最近3个月上海区域内的充电桩招标信息都有哪些，请汇总后每天9:00发送给我
```

点击创建订阅。

展示订阅表：

- 问题。
- 计划。
- 状态。
- 最近运行时间。
- 手动触发按钮。

点击手动触发一次，展示 Outbox 新 Word。

再次手动触发，展示：

- 第二次执行仍有 run 记录。
- `sent_history` 防止重复推送。
- 报告只包含新增内容，或显示零新增。

## 7. 镜头五：登录站说明

执行或展示命令：

```powershell
python -m tendertrace login-qianlima
python -m tendertrace verify-qianlima
```

讲解：

- 系统打开浏览器。
- 用户手动登录免费会员。
- 保存 Playwright `storage_state`。
- 不保存账号密码。
- 登录态失效时，重新执行 `login-qianlima` 后再做 live 校验；公开源仍可继续运行。

## 8. 镜头六：反硬编码证据

展示 CLI：

```powershell
python -m tendertrace run-once "最近10天全国设备招标信息都有哪些" --max-pages 1 --max-results 4
```

展示 SQLite 或 API 证据：

```text
GET /api/runs/{run_id}
GET /api/traces/{run_id}
GET /api/checkpoints/{run_id}
```

讲解：

- 每次运行都有唯一 Run ID。
- trace 中有真实来源采集事件。
- Word 是运行后生成的，不是静态文件。
- `model_audits` 只保存模型调用状态和哈希，不保存 key。

## 9. 建议视频结构

| 时间 | 内容 |
|---|---|
| 00:00-00:30 | 项目目标和 Web 工作台 |
| 00:30-01:00 | 配置、来源、模型状态 |
| 01:00-02:30 | 立即执行并生成 Word |
| 02:30-03:30 | Trace 和 Word 内容验证 |
| 03:30-04:30 | 第二个问题 |
| 04:30-05:30 | 数据源健康、入口路由和发现规则 |
| 05:30-06:30 | 定时订阅与增量 |
| 06:30-07:00 | 登录态来源说明 |
| 07:00-07:40 | 测试、Ruff、反硬编码证据 |

## 10. 演示验收点

- 至少展示两个自然语言问题。
- 至少生成一个 Word 并打开。
- 展示 outbox 下载。
- 展示事件流。
- 展示模型状态。
- 展示来源状态、入口路由、发现规则和抓取健康。
- 展示订阅与增量，可用 `python -m tendertrace demo-incremental "最近3个月上海充电桩招标信息有哪些，请每天9:00发送给我" --max-pages 1 --max-results 5` 快速生成两次运行证据。
- 展示测试通过。
- 展示 `acceptance-check` 无 fail。
- 不在视频中展示 API key、账号密码或 `.env.local` 明文。
