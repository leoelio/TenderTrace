# TenderTrace

<p align="center">
  <strong>Language / 语言：</strong>
  <a href="#中文说明">中文</a> |
  <a href="#english-readme">English</a>
</p>

<p align="center">
  <strong>Current stage: P28</strong> · Compact Workbench · Feishu Report Delivery · Delivery Audit
</p>

---

<details open>
<summary id="中文说明"><strong>中文说明</strong></summary>

## 项目简介

TenderTrace 是一个面向招投标情报聚合场景的可运行 AI 应用原型。系统支持用户输入自然语言问题，自动解析主题、地区、时间范围和调度意图，从多源招投标网站采集公告，清洗去重后生成 Word 报告，并通过 Web 下载与本地 outbox 交付。

可选配置 SMTP 后，系统也可以把生成后的 Word 作为邮件附件发送；订阅页会展示新增条数、已跳过历史条数、下次触发时间和最近 Word 下载入口，便于验证“持续订阅 + 增量推送”。

项目当前已经从“用户查询时现场抓取”升级为“先采集入库，后本地检索”的架构：后台采集任务持续写入 SQLite，用户查询优先走本地 FTS5 索引，不足时再触发现场采集。评测层也支持人工金标集驱动的真实 Recall@K。

## 核心能力

- 自然语言意图解析：识别主题、同义词、地区、省市区、时间范围、发送频率。
- 多源采集：支持中国政府采购网、全国公共资源交易平台、千里马登录态源。
- 托管抓取：统一 retry、阻断识别、浏览器兜底、批量详情抓取和页面快照。
- 登录态管理：千里马使用 Playwright `storage_state` 保存登录状态，代码不保存账号密码。
- 本地优先检索：公告入库后写入 SQLite FTS5，使用 jieba 分词和 BM25 排序。
- 后台采集订阅：采集订阅与用户报告订阅分离，只负责持续养大 `notices` 库。
- 增量推送：用户订阅通过 `sent_history` 保证已经发送过的公告不重复出现在后续 Word。
- 邮件投递：可选 SMTP 通道，将订阅/运行生成的 Word 作为附件发送。
- 飞书台账：可选同步新增公告到飞书多维表格，形成招标机会协同跟进表。
- 飞书协同：Word 报告、定时订阅和用户周报可发送到默认会话，发送结果写入本地交付账本。
- 清洗去重：正文噪声清理、URL 规范化、项目编号提取、SimHash 聚类。
- 附件抽取：支持受限下载并抽取 PDF、DOCX、XLSX 正文片段。
- 证据链：保存来源链接、正文摘录、附件快照、字段级证据和事实校验结果。
- Word 报告：输出标题、发布时间、来源链接、核心内容、附件链接、多源覆盖和抓取健康。
- 模型增强：支持规则模式、本地 Ollama 模式、OpenAI 兼容云端模式。
- Agent 评测：覆盖 RAG、Agent、Harness、Recall Proxy、金标 Recall@K。
- 用户记忆库：记录查询、点击、下载、订阅和运行行为，生成知识画像、风险信号和可执行建议。
- 可选向量检索：安装 `.[vector]` 后可用 BGE 类模型生成本地向量，与 FTS 做 RRF 融合。

## 技术栈

| 模块 | 技术 |
|---|---|
| Web/API | FastAPI, Uvicorn |
| 前端 | 静态 HTML/CSS/JavaScript |
| 数据库 | SQLite, WAL, FTS5 |
| 调度 | APScheduler |
| 抓取 | httpx, Playwright, selectolax, trafilatura |
| 意图解析 | 规则解析, jieba, 行政区划字典, 品类同义词 |
| 报告 | python-docx |
| 附件 | pypdf, openpyxl |
| 模型 | Ollama, OpenAI-compatible API |
| 向量增强 | sentence-transformers, optional extra |
| 测试 | unittest, Ruff |

## 目录结构

```text
tendertrace/
  adapters/              # 多源采集适配器
  app/                   # FastAPI 应用
  intent/                # BidQL 意图解析
  llm/                   # 本地/云端模型网关与审计
  pipeline/              # 清洗、去重、附件、证据链
  report/                # Word 报告生成
  runtime/               # TenderGraph 状态图、事件和 checkpoint
  scheduling/            # 用户订阅、采集订阅、sent_history
  vault/                 # 千里马 storage_state 管理
  db.py                  # SQLite schema 与迁移
  fetching.py            # 托管 HTTP 抓取、重试、阻断识别和批量详情抓取
  linking.py             # URL Map / LinkExtractor 发现规则
  memory.py              # 用户记忆库、知识画像和生成式建议
  retrieval.py           # FTS5 / LIKE / 向量融合检索
  runner.py              # 一次完整运行流程
  source_map.py          # 数据源地图和来源健康统计
  gold.py                # 金标 Recall@K 评测
  vector.py              # 可选向量构建与覆盖率
web/dist/                # Web 工作台静态文件
tests/                   # 单元测试
docs/                    # 设计、操作、教学和评测文档
```

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
copy .env.example .env.local
.\.venv\Scripts\python -m tendertrace init-db
.\.venv\Scripts\python -m tendertrace config-check
.\.venv\Scripts\python -m tendertrace serve
```

默认 Web 地址：

```text
http://127.0.0.1:8000/
```

如果端口被占用：

```powershell
$env:TENDERTRACE_PORT='8001'
python -m tendertrace serve
```

## 关键配置

`.env.local` 用于本地运行配置，不应提交到仓库。

```env
TENDERTRACE_APP_ENV=dev
TENDERTRACE_HOST=127.0.0.1
TENDERTRACE_PORT=8000
TENDERTRACE_TIMEZONE=Asia/Shanghai

TENDERTRACE_DB_PATH=data/tendertrace.sqlite3
TENDERTRACE_OUTPUTS_DIR=outputs
TENDERTRACE_OUTBOX_DIR=outbox
TENDERTRACE_SNAPSHOTS_DIR=snapshots
TENDERTRACE_TRACES_DIR=traces
TENDERTRACE_SECRETS_DIR=secrets
TENDERTRACE_DELIVERY_CHANNELS=web,outbox

TENDERTRACE_MODEL_MODE=local
TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=false
TENDERTRACE_OLLAMA_BASE_URL=http://127.0.0.1:11434
TENDERTRACE_OLLAMA_MODEL=qwen3:8b

OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.5
TENDERTRACE_OPENAI_API_STYLE=responses

# 可选邮件投递。启用前把 email 加入 TENDERTRACE_DELIVERY_CHANNELS。
TENDERTRACE_SMTP_HOST=
TENDERTRACE_SMTP_PORT=587
TENDERTRACE_SMTP_USERNAME=
TENDERTRACE_SMTP_PASSWORD=
TENDERTRACE_SMTP_FROM=
TENDERTRACE_SMTP_TO=
TENDERTRACE_SMTP_USE_TLS=true

# 可选飞书多维表格台账。启用前把 feishu_bitable 加入 TENDERTRACE_DELIVERY_CHANNELS。
# 未单独配置 App ID/Secret 时，会自动复用下方 FEISHU_APP_ID/FEISHU_APP_SECRET。
TENDERTRACE_FEISHU_APP_ID=
TENDERTRACE_FEISHU_APP_SECRET=
TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=
TENDERTRACE_FEISHU_BITABLE_TABLE_ID=
TENDERTRACE_PUBLIC_BASE_URL=http://127.0.0.1:8000
TENDERTRACE_API_TOKEN=

# 可选飞书消息/群聊接口。
FEISHU_ENABLED=false
FEISHU_BASE_URL=https://open.feishu.cn
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_DEFAULT_RECEIVE_ID=
FEISHU_DEFAULT_RECEIVE_ID_TYPE=chat_id
```

模型模式：

- `disabled`：完全不调用模型，只使用规则解析。
- `local`：使用 Ollama，本地增强主题词。
- `cloud`：使用 OpenAI 兼容接口。

## 常用命令

初始化数据库：

```powershell
python -m tendertrace init-db
```

查看安全配置摘要：

```powershell
python -m tendertrace config-check
```

解析自然语言意图：

```powershell
python -m tendertrace parse-intent "最近1个月上海充电桩招标信息有哪些"
```

运行一次查询并生成 Word：

```powershell
python -m tendertrace run-once "最近1个月上海充电桩招标信息有哪些" --max-pages 2 --max-results 8
```

只采集入库，不生成报告：

```powershell
python -m tendertrace ingest-once --topic 充电桩 --region 上海 --window-days 30 --max-pages 1 --max-results 20
```

创建用户订阅：

```powershell
python -m tendertrace create-subscription "最近3个月上海充电桩招标信息有哪些，请每天9:00发送给我" --max-pages 1 --max-results 5
```

启用邮件投递时，先在 `.env.local` 配置 SMTP，并把发送渠道改为：

```env
TENDERTRACE_DELIVERY_CHANNELS=web,outbox,email
```

启用飞书多维表格台账时，先在 `.env.local` 配置飞书应用与表格参数，并检查连接：

```powershell
python -m tendertrace feishu-bitable-check
python -m tendertrace feishu-bitable-check --ensure-fields
```

演示订阅增量二次运行：

```powershell
python -m tendertrace demo-incremental "最近3个月上海充电桩招标信息有哪些，请每天9:00发送给我" --max-pages 1 --max-results 5
```

创建后台采集订阅：

```powershell
python -m tendertrace create-ingest-subscription --name 上海充电桩采集 --topic 充电桩 --region 上海 --cron "0 */6 * * *"
python -m tendertrace list-ingest-subscriptions
python -m tendertrace run-ingest-subscription <ingest_subscription_id>
```

检查模型状态：

```powershell
python -m tendertrace model-status
python -m tendertrace model-doctor
```

检查飞书集成状态与发送测试消息：

```powershell
python -m tendertrace feishu-status
python -m tendertrace feishu-list-chats --page-size 20
python -m tendertrace feishu-send-text --text "TenderTrace 飞书联调消息"
```

生成用户记忆周报与画像快照：

```powershell
python -m tendertrace memory-weekly --days 7 --save
```

千里马登录态保存与验证：

```powershell
python -m tendertrace login-qianlima
python -m tendertrace verify-qianlima
python -m tendertrace verify-qianlima --live
```

金标候选包与真实召回评测：

```powershell
python -m tendertrace gold-candidates --max-pages 2 --max-results 30 --out docs/evaluation/gold_candidates_latest.json
python -m tendertrace gold-coverage --out docs/evaluation/gold_coverage_latest.json
python -m tendertrace evaluate-gold --out docs/evaluation/recall_after_p23.json
```

可选向量检索：

```powershell
python -m pip install -e .[vector]
python -m tendertrace embed-notices
```

## 飞书集成

飞书集成默认关闭。创建飞书自建应用并开启机器人能力后，在 `.env.local` 填入 `FEISHU_APP_ID` 与 `FEISHU_APP_SECRET`，再把 `FEISHU_ENABLED` 改为 `true`。真实密钥不要写入 `.env.example`、README 或代码。

可用 Web API：

- `GET /api/integrations/feishu/status`：查看脱敏后的配置状态。
- `GET /api/integrations/feishu/overview`：统一查看消息、报告、多维表格、智能体和最近交付状态。
- `GET /api/integrations/feishu/chats?page_size=20`：列出机器人所在群，用于获取 `chat_id`。
- `POST /api/integrations/feishu/receiver`：保存默认接收会话；响应不会返回 `receive_id`。
- `POST /api/integrations/feishu/test-message`：发送一条显式测试消息。
- `POST /api/outbox/{filename}/send-feishu`：上传并发送指定 Word 报告。
- `POST /api/memory/weekly/send-feishu`：发送最近一周的使用摘要与建议。

设置页的“飞书连接中心”可以从机器人已加入的会话中选择默认接收目标。立即运行或订阅勾选“同时发送飞书”后，生成的 Word 会自动投递；每次成功或失败都会记录时间、文件和错误原因。若平台返回 `232034`，需要先在飞书开放平台发布应用并确认当前租户已经安装。

## Web 工作台

Web UI 覆盖以下视图：

- 工作台：输入自然语言问题，选择立即运行或订阅以及 Web/飞书交付；模型策略和搜索深度收纳在高级设置中。
- 历史运行：查看 run 记录、trace、checkpoint 和报告路径。
- 订阅管理：管理用户定时报告订阅，查看新增/跳过历史、下次触发时间和最近 Word。
- 数据源：查看公开源、千里马登录态、入口路由、发现规则和来源健康。
- Agent 评测：查看 RAG、Agent、Harness、Recall、金标评测和向量覆盖率。
- 用户记忆：查看使用画像、知识偏好、风险信号和生成式行动建议。
- 设置：查看运行配置、模型连通性和飞书消息/报告/多维表格/智能体状态。

## 本地库检索流程

```text
后台采集 / 用户查询补采
        ↓
notices 表持久化
        ↓
notices_fts 全文索引
        ↓
用户查询优先本地检索
        ↓
库内结果不足时补充现场采集
        ↓
清洗去重 / 证据校验 / Word 报告
```

本地检索使用：

- jieba 搜索分词。
- SQLite FTS5 倒排索引。
- BM25 排序。
- 省市区别名过滤。
- 可选向量召回与 RRF 融合。

## 评测体系

TenderTrace 的评测分为四类：

- RAG：证据通过率、附件抽取率、报告产出率。
- Agent：checkpoint 完成率、trace 事件数、失败率。
- Harness：固定自然语言样例的 BidQL 字段准确率。
- Recall：代理召回指标、FTS 覆盖率、本地复用率、向量覆盖率、金标 Recall@K。

金标文件位于：

```text
docs/evaluation/gold_benchmark.json
```

注意：`gold_notices` 必须由人工打开源站核验后填写，不能用系统自身召回结果自动回填。

## 安全边界

以下内容不应提交到公开仓库：

- `.env.local`
- `.env`
- `secrets/`
- `data/`
- `outputs/`
- `outbox/`
- `snapshots/`
- `traces/`
- `dist/`
- Playwright `storage_state`
- 任何真实 API key、cookie、账号密码或本地数据库

`.env.example` 中的 `OPENAI_API_KEY` 必须保持为空。

## 验证

当前验证基线：

- Current stage: P27
- 143 unit tests pass.
- Ruff passes.
- `node --check web\dist\app.js` passes.
- `python -m tendertrace acceptance-check --no-runtime` passes.
- `python -m tendertrace preflight --no-package` passes.

推荐回归命令：

```powershell
python -m pytest
python -m ruff check .
node --check web\dist\app.js
python -m tendertrace acceptance-check --no-runtime
python -m tendertrace preflight --no-package
python -m tendertrace preflight --no-package --live
```

</details>

---

<details>
<summary id="english-readme"><strong>English README</strong></summary>

## Overview

TenderTrace is a runnable AI application prototype for tender and procurement intelligence aggregation. A user can enter a natural-language query, and the system parses topic, region, time range, and scheduling intent, collects tender notices from multiple sources, cleans and deduplicates the results, and generates a Word report for Web download, local outbox delivery, and optional SMTP email delivery.

When SMTP is configured, generated Word reports can be sent as email attachments. The subscription page also surfaces new/skipped counts, next run time, latest Word download, and the latest email status for incremental delivery verification.

The current architecture is local-first: background ingestion continuously stores notices into SQLite, user queries first search the local FTS5 index, and live crawling is triggered only when the local database cannot satisfy the request. The evaluation layer also supports real Recall@K based on manually annotated gold sets.

## Key Features

- Natural-language intent parsing for topic, synonyms, region, time range, and delivery schedule.
- Multi-source collection from public procurement platforms and a Qianlima login-state source.
- Login-state vault based on Playwright `storage_state`; credentials are never stored in code.
- Local-first retrieval with SQLite FTS5, jieba tokenization, and BM25 ranking.
- Background ingest subscriptions separated from user report subscriptions.
- Incremental scheduled delivery with `sent_history` deduplication.
- Optional SMTP email delivery for generated Word reports.
- Optional Feishu Bitable opportunity ledger for incremental tender records.
- Text cleaning, URL canonicalization, project-number extraction, SimHash clustering.
- Bounded attachment download and extraction for PDF, DOCX, and XLSX.
- Evidence chain with source links, excerpts, attachment snapshots, and fact checks.
- Word report generation with title, publish time, source link, core content, and attachment links.
- Rule-only, local Ollama, and OpenAI-compatible cloud model enhancement modes.
- Agent evaluation covering RAG, agent execution, intent harness, recall proxy, and gold Recall@K.
- User memory knowledge base that records queries, clicks, downloads, subscriptions, and runs, then generates preference profiles, risk signals, and actionable advice.
- Optional vector retrieval via `sentence-transformers`, fused with FTS by RRF.

## Tech Stack

| Area | Technology |
|---|---|
| Web/API | FastAPI, Uvicorn |
| Frontend | Static HTML/CSS/JavaScript |
| Database | SQLite, WAL, FTS5 |
| Scheduler | APScheduler |
| Crawling | httpx, Playwright, selectolax, trafilatura |
| Intent Parsing | Rules, jieba, administrative-division dictionary, category synonyms |
| Reports | python-docx |
| Attachments | pypdf, openpyxl |
| Models | Ollama, OpenAI-compatible API |
| Vector Search | sentence-transformers, optional extra |
| Tests | unittest, Ruff |

## Project Structure

```text
tendertrace/
  adapters/              # Source adapters
  app/                   # FastAPI app
  intent/                # BidQL intent compiler
  llm/                   # Model gateway and audit records
  pipeline/              # Cleaning, deduplication, attachments, evidence
  report/                # Word report writer
  runtime/               # TenderGraph, events, checkpoints
  scheduling/            # User subscriptions, ingest subscriptions, sent_history
  vault/                 # Qianlima storage_state vault
  db.py                  # SQLite schema and migrations
  memory.py              # User memory, knowledge profile, and generated advice
  retrieval.py           # FTS5 / LIKE / vector-fused retrieval
  runner.py              # End-to-end run orchestration
  gold.py                # Gold-set Recall@K evaluation
  vector.py              # Optional local vector indexing
web/dist/                # Static Web UI
tests/                   # Unit tests
docs/                    # Design, operation, teaching, and evaluation docs
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
copy .env.example .env.local
.\.venv\Scripts\python -m tendertrace init-db
.\.venv\Scripts\python -m tendertrace config-check
.\.venv\Scripts\python -m tendertrace serve
```

Default Web URL:

```text
http://127.0.0.1:8000/
```

If port 8000 is occupied:

```powershell
$env:TENDERTRACE_PORT='8001'
python -m tendertrace serve
```

## Configuration

Use `.env.local` for local runtime configuration. Do not commit it.

```env
TENDERTRACE_APP_ENV=dev
TENDERTRACE_HOST=127.0.0.1
TENDERTRACE_PORT=8000
TENDERTRACE_TIMEZONE=Asia/Shanghai

TENDERTRACE_DB_PATH=data/tendertrace.sqlite3
TENDERTRACE_OUTPUTS_DIR=outputs
TENDERTRACE_OUTBOX_DIR=outbox
TENDERTRACE_SNAPSHOTS_DIR=snapshots
TENDERTRACE_TRACES_DIR=traces
TENDERTRACE_SECRETS_DIR=secrets

TENDERTRACE_MODEL_MODE=local
TENDERTRACE_MODEL_ENHANCEMENT_ENABLED=false
TENDERTRACE_OLLAMA_BASE_URL=http://127.0.0.1:11434
TENDERTRACE_OLLAMA_MODEL=qwen3:8b

OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.5
TENDERTRACE_OPENAI_API_STYLE=responses
TENDERTRACE_API_TOKEN=

# Optional Feishu messaging/chat integration.
FEISHU_ENABLED=false
FEISHU_BASE_URL=https://open.feishu.cn
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_DEFAULT_RECEIVE_ID=
FEISHU_DEFAULT_RECEIVE_ID_TYPE=chat_id
```

Model modes:

- `disabled`: rule-only parsing, no model call.
- `local`: Ollama-based local enhancement.
- `cloud`: OpenAI-compatible cloud enhancement.

## Common Commands

Initialize the database:

```powershell
python -m tendertrace init-db
```

Print safe configuration:

```powershell
python -m tendertrace config-check
```

Parse intent:

```powershell
python -m tendertrace parse-intent "Tender notices for EV charging piles in Shanghai in the last month"
```

Run one query and generate a Word report:

```powershell
python -m tendertrace run-once "最近1个月上海充电桩招标信息有哪些" --max-pages 2 --max-results 8
```

Ingest into the local database without generating a report:

```powershell
python -m tendertrace ingest-once --topic 充电桩 --region 上海 --window-days 30 --max-pages 1 --max-results 20
```

Create a user report subscription:

```powershell
python -m tendertrace create-subscription "最近3个月上海充电桩招标信息有哪些，请每天9:00发送给我" --max-pages 1 --max-results 5
```

Create a background ingest subscription:

```powershell
python -m tendertrace create-ingest-subscription --name shanghai-charging-ingest --topic 充电桩 --region 上海 --cron "0 */6 * * *"
python -m tendertrace list-ingest-subscriptions
python -m tendertrace run-ingest-subscription <ingest_subscription_id>
```

Check model status:

```powershell
python -m tendertrace model-status
python -m tendertrace model-doctor
```

Check Feishu integration status and send a test message:

```powershell
python -m tendertrace feishu-status
python -m tendertrace feishu-list-chats --page-size 20
python -m tendertrace feishu-send-text --text "TenderTrace Feishu smoke message"
```

Build and persist a user-memory weekly profile snapshot:

```powershell
python -m tendertrace memory-weekly --days 7 --save
```

Save and verify Qianlima login state:

```powershell
python -m tendertrace login-qianlima
python -m tendertrace verify-qianlima
python -m tendertrace verify-qianlima --live
```

Generate gold candidates and evaluate Recall@K:

```powershell
python -m tendertrace gold-candidates --max-pages 2 --max-results 30 --out docs/evaluation/gold_candidates_latest.json
python -m tendertrace gold-coverage --out docs/evaluation/gold_coverage_latest.json
python -m tendertrace evaluate-gold --out docs/evaluation/recall_after_p23.json
```

Enable optional vector retrieval:

```powershell
python -m pip install -e .[vector]
python -m tendertrace embed-notices
```

## Feishu Integration

Feishu integration is disabled by default. After creating a custom Feishu app and enabling bot capability, put `FEISHU_APP_ID` and `FEISHU_APP_SECRET` in `.env.local`, then set `FEISHU_ENABLED=true`. Never commit real credentials to `.env.example`, README, or source code.

The Bitable integration reuses `FEISHU_APP_ID` and `FEISHU_APP_SECRET` by default. Set `TENDERTRACE_FEISHU_APP_ID` and `TENDERTRACE_FEISHU_APP_SECRET` only when Bitable uses a separate app.

Available Web APIs:

- `GET /api/integrations/feishu/status`: inspect redacted integration status.
- `GET /api/integrations/feishu/overview`: inspect messaging, report, Bitable, agent, and recent delivery status.
- `GET /api/integrations/feishu/chats?page_size=20`: list groups where the bot is a member and find `chat_id`.
- `POST /api/integrations/feishu/receiver`: persist the default destination without returning its ID.
- `POST /api/integrations/feishu/test-message`: send one explicit test message.
- `POST /api/outbox/{filename}/send-feishu`: upload and send a Word report.
- `POST /api/memory/weekly/send-feishu`: send the weekly usage digest and recommendations.

The Feishu connection center can select a default chat from the bot's visible chats. Queries and subscriptions can opt into automatic Word delivery, while every success or failure is written to the local delivery ledger. Error `232034` means the app must be published and installed in the current tenant first.

## Web Workbench

The Web UI includes:

- Workbench: enter natural-language queries, choose immediate or scheduled execution, and select Web/Feishu delivery; model and retrieval controls stay under advanced settings.
- Run history: inspect runs, trace events, checkpoints, and report paths.
- Subscription management: manage scheduled user report subscriptions.
- Data sources: inspect public sources and Qianlima login-state status.
- Agent evaluation: inspect RAG, agent, harness, recall, gold-set metrics, and vector coverage.
- User memory: inspect usage profiles, knowledge preferences, risk signals, and generated next-step advice.
- Settings: inspect runtime, model, Feishu messaging/report, Bitable, and agent connectivity.

## Local-First Retrieval Flow

```text
Background ingest / live collection
        ↓
Persist notices
        ↓
Build notices_fts index
        ↓
Search local database first
        ↓
Live crawl only when local results are insufficient
        ↓
Clean, deduplicate, validate evidence, generate Word
```

Local retrieval uses:

- jieba search tokenization.
- SQLite FTS5 inverted index.
- BM25 ranking.
- Administrative-region aliases.
- Optional vector recall with RRF fusion.

## Evaluation System

TenderTrace evaluates four dimensions:

- RAG: grounding pass rate, attachment extraction rate, report yield.
- Agent: checkpoint completion rate, trace event count, failure rate.
- Harness: BidQL field accuracy on fixed natural-language cases.
- Recall: recall proxy, FTS coverage, local reuse, vector coverage, gold-set Recall@K.

Gold benchmark path:

```text
docs/evaluation/gold_benchmark.json
```

Important: `gold_notices` must be filled by a human after verifying source pages. Do not auto-fill gold labels from the system's own retrieval results.

## Security Boundaries

Do not commit:

- `.env.local`
- `.env`
- `secrets/`
- `data/`
- `outputs/`
- `outbox/`
- `snapshots/`
- `traces/`
- `dist/`
- Playwright `storage_state`
- Real API keys, cookies, credentials, or local SQLite databases

The `OPENAI_API_KEY` field in `.env.example` must stay blank.

## Verification

Current verified baseline:

- Current stage: P27
- 143 unit tests pass.
- Ruff passes.
- `node --check web\dist\app.js` passes.
- `python -m tendertrace acceptance-check --no-runtime` passes.
- `python -m tendertrace preflight --no-package` passes.

Recommended checks:

```powershell
python -m pytest
python -m ruff check .
node --check web\dist\app.js
python -m tendertrace acceptance-check --no-runtime
python -m tendertrace preflight --no-package
python -m tendertrace preflight --no-package --live
```

</details>
