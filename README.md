# TenderTrace

<p align="center">
  <strong>Language / 语言：</strong>
  <a href="#中文说明">中文</a> |
  <a href="#english-readme">English</a>
</p>

<p align="center">
  <strong>Current stage: P47</strong> · Stakeholder Intelligence · Evidence-backed Account Strategy · Relationship Risk Gates
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
- 多源采集：支持中国政府采购网、全国公共资源交易平台、千里马登录态源、TED、UNGM、世界银行、亚洲开发银行、非洲开发银行、欧洲复兴开发银行 ECEPP、美洲开发银行，以及英国 Contracts Finder / Find a Tender 官方接口，共 12 个来源；UNGM 一处覆盖 32 个联合国组织。
- 范围路由：国内、省市查询只启用国内源；英国、欧盟、世界银行、亚洲开发银行、非洲开发银行、美洲开发银行和全球查询自动启用对应国际源，避免无效抓取和地域误匹配。
- 托管抓取：统一阻断识别、`Retry-After`、指数退避、HTTP 优先、Playwright 动态页恢复、静态资源拦截、批量详情抓取和页面快照。
- 登录态管理：千里马使用 Playwright `storage_state` 保存登录状态，代码不保存账号密码；会员检索会提交真实主题并监听同域 API 鉴权，过期会话明确标记为 `login_expired`，不会伪装成零结果。
- 本地优先检索：公告入库后写入 SQLite FTS5，使用 jieba 分词和 BM25 排序。
- 后台采集订阅：采集订阅与用户报告订阅分离，只负责持续养大 `notices` 库；主题与区域经过规范化并使用稳定身份，重复请求不会创建重复采集计划。
- 增量推送：用户订阅通过 `sent_history` 保证已经发送过的公告不重复出现在后续 Word。
- 邮件投递：可选 SMTP 通道，将订阅/运行生成的 Word 作为附件发送。
- 飞书台账：可选同步新增公告到飞书多维表格，形成招标机会协同跟进表。
- 飞书伙伴线索：多维表格中标记为“伙伴提交”或“待导入”的记录可经预检后进入本地公告库、FTS 和证据链；系统核验公网原文、保存内容哈希与正文摘录，并回写稳定指纹、入库及核验状态。系统自身同步记录不会循环导入。
- 飞书协同：Word、周报和可操作机会卡片可发送到默认会话；点击“认领机会”会为点击者创建或复用幂等 Task v2，并按配置同步截止日程。任务完成后，系统向负责人发送下一步机会卡；任务逾期时按天定向催办，继续资格确认或 Go/Hold/No-Go 决策。卡片动作通过 HTTP 或官方长连接回写本地状态流、多维表格与审计事件。
- 飞书接收目标：连接中心同时读取机器人可见会话和应用授权通讯录成员，可将群聊或成员设为统一默认目标，报告、周报、经营晨报和来源告警复用该偏好。
- 飞书会话入口：用户可直接在机器人会话中输入自然语言问题；即时查询回传 Word，带频率的问题创建绑定当前会话的增量订阅，事件支持持久化去重与中断恢复。
- 机会情报：基于真实字段、时效、证据质量与多源佐证计算机会等级，输出负责人、团队和伙伴行动建议。
- 机会团队治理：负责人保持唯一责任人，方案、商务、交付、法务和伙伴负责人作为独立协作角色维护；系统按销售阶段动态计算团队覆盖与角色缺口，低于配置阈值时阻断 Go 决策。
- 飞书团队协同：内部团队与伙伴成员以 Task v2 `follower` 身份增删，不与 `assignee` 负责人混淆；同步状态、失败原因和审计事件持久化，多维表格同步展示团队、伙伴、覆盖率和缺口。
- 客户关系图谱：结构化维护经济决策人、技术决策人、采购执行人、内部支持者、业务使用者和关键阻力人；记录影响力、立场、关系强度、内部责任人、下一步行动及证据来源，不采集手机号或邮箱。
- 关系策略闭环：关键人事实必须附证据来源与摘录；系统按销售阶段计算关系覆盖和健康度，识别高影响抵触者、立场未知与角色缺口，生成基于真实关系数据的行动建议并进入 Go 门禁。
- 事实核验闭环：分析人员可在 Web 补充采购主体、项目编号、预算、截止时间和地区，并附原文链接与证据摘录；系统保留原始公告，以可审计覆盖层重算完整度、机会等级与销售准入，再同步飞书多维表格。
- 销售准入：以负责人、采购主体、可信度、完整度、投标窗口、机会评分、需求覆盖、阶段团队覆盖和关键关系覆盖形成可解释门禁；阈值由运行配置管理，只有阶段、资料、团队与客户关系条件同时满足才允许推进。
- 投标决策：Go/Hold/No-Go 与决策人、依据、时间持久化到 SQLite，并同步到 Web、飞书共享卡片和多维表格；策略制定阶段按独立阶段时钟执行决策 SLA，超时进入管理升级队列，可手动或定时发送幂等飞书摘要。
- 机会经营晨报：把机会等级、负责人缺口、资格门禁、截止时间、决策 SLA、市场信号和来源健康合并成可操作飞书卡片；支持工作日自动发送、按接收会话独立去重和卡片内直接推进机会。
- 行动队列：按机会等级、负责人缺失和投标截止时间动态排序，集中展示待认领重点、七日内截止与已启动协同线索。
- 来源可观测性：逐源统计真实尝试、正确跳过、运行命中、请求成功率、延迟和综合可靠性，国际/国内范围路由不再污染失败率。
- 来源可信度：把来源权威性、真实采集可靠度、原文证据、独立来源印证和附件快照合成为可解释评分；零运行样本明确标记为“未观察”，不会伪装成高可靠，低可信结论直接进入销售准入门禁。Web、飞书机会卡和多维表格记录视图展示同一依据。
- 来源 SLO 闭环：依据登录态、真实运行可靠度和最近成功时间识别异常；Web 可发送去重飞书告警，也可一键创建带负责人和处置 SLA 的 Task v2 任务。事件进入本地处置台账，只有飞书任务完成且来源真实恢复才关闭。
- 市场研判：使用最近 500 条本地公告形成同品类预算基准、客户集中度和采购阶段分布；样本不足时明确降级，不生成伪精确结论。
- 竞争情报：从结果/合同公告提取成交供应商、成交金额和证据摘录，聚合同品类历史供应商；无法可靠提取时明确标记样本不足。
- 需求审阅：按技术规格、兼容集成、交付实施、验收、服务、资质、评分和安全 8 个维度检查当前采集文本，并给出待核对项与优化建议。
- 飞书记录视图：切换多维表格记录时同步读取本地机会库的负责人、销售阶段、资格门禁、投标决策与任务状态；可回写研判、提交证据核验，并在同一视图执行阶段有效的 Go/Hold/No-Go、投标准备、结果和归档动作。首次认领必须通过交互卡获取成员真实 `open_id`，不会把 Base 用户标识误作任务负责人。
- 统一动作契约：工作流域层根据销售阶段、资格门禁与 Go 决策动态生成带版本的动作清单、阻断原因、展示语义和身份要求；Web、飞书卡片与记录视图消费同一契约，不再各自硬编码流程分支。
- 公告持续跟踪：重复采集使用原位 UPSERT，保留机会负责人、核验事实、事件和创建时间；预算、截止时间、正文或附件等业务变化写入不可变修订账本，机会列表与详情展示最近差异。
- 变更提醒：修订按机会负责人聚合为飞书提醒；失败可重试，成功按“修订 + 接收人”去重，终态机会保持静默，无负责人时才回退到统一接收目标。
- 重大变更治理：已进入销售流程的机会发生预算、截止时间、采购主体、项目编号、正文或附件变化时自动生成复核账本，原 Go/Hold 结论失效；Web、飞书卡片和多维表格记录视图消费同一动作契约，负责人确认复核后重新启动决策 SLA，逾期项进入统一管理升级。
- 清洗去重：正文噪声清理、URL 规范化、项目编号提取、SimHash 聚类。
- 附件抽取：支持受限下载并抽取 PDF、DOCX、XLSX 正文片段。
- 证据链：保存来源链接、正文摘录、附件快照、字段级证据和事实校验结果。
- Word 报告：输出标题、发布时间、来源链接、核心内容、附件链接、多源覆盖和抓取健康。
- 模型增强：支持规则模式、本地 Ollama 模式、OpenAI 兼容云端模式。
- Agent 评测：覆盖 RAG、Agent、Harness、Recall Proxy、金标 Recall@K；人工金标未完成时固定标记“未就绪”，代理分不替代严格召回验收。
- 用户记忆库：记录查询、点击、下载、订阅和运行行为，生成知识画像、风险信号和可执行建议；采纳知识库建议会把核心区域/主题转成幂等 APScheduler 采集订阅，采纳高频查询建议会创建每日 09:00 的增量用户订阅，并在 Web 与飞书展示真实执行结果。
- 机会建议自动化：采纳 A 级跟进或 B 级确认建议会发送真实机会经营简报；飞书卡片操作绑定当前群聊，Web 操作使用默认协作目标，重复采纳由会话级投递账本去重。
- 飞书原会话订阅：用户在周报卡片中采纳高频查询建议时，订阅自动绑定卡片所在群聊，后续 Word 依赖 `sent_history` 仅向该会话推送新增内容；相同查询、计划、渠道和接收目标会复用同一订阅。
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
  opportunity.py         # 机会质量评分、定级、风险和角色行动
  workflow.py            # 销售机会阶段、负责人、任务/日程标识和动作审计
  retrieval.py           # FTS5 / LIKE / 向量融合检索
  runner.py              # 一次完整运行流程
  source_map.py          # 数据源地图和来源健康统计
  source_trust.py        # 来源权威性、运行可靠度与证据印证评分
  gold.py                # 金标 Recall@K 评测
  vector.py              # 可选向量构建与覆盖率
web/dist/                # Web 工作台静态文件
integrations/feishu-record-view/ # 飞书多维表格记录视图插件
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
TENDERTRACE_FEISHU_BITABLE_BASE_URL=
TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=false
TENDERTRACE_FEISHU_LEAD_IMPORT_CRON=*/15 * * * *
TENDERTRACE_PUBLIC_BASE_URL=http://127.0.0.1:8000
TENDERTRACE_API_TOKEN=

# 销售准入阈值与策略制定阶段的管理决策 SLA。
TENDERTRACE_QUALIFICATION_MIN_OPPORTUNITY_SCORE=65
TENDERTRACE_QUALIFICATION_MIN_CREDIBILITY=60
TENDERTRACE_QUALIFICATION_MIN_COMPLETENESS=55
TENDERTRACE_QUALIFICATION_MIN_REQUIREMENT_COVERAGE=40
TENDERTRACE_QUALIFICATION_MIN_TEAM_COVERAGE=60
TENDERTRACE_QUALIFICATION_MIN_STAKEHOLDER_COVERAGE=50
TENDERTRACE_DECISION_SLA_HOURS=24
TENDERTRACE_CHANGE_REVIEW_SLA_HOURS=8
TENDERTRACE_OPPORTUNITY_ESCALATION_ENABLED=false
TENDERTRACE_OPPORTUNITY_ESCALATION_CRON=0 9,14 * * 1-5
TENDERTRACE_OPPORTUNITY_BRIEFING_ENABLED=false
TENDERTRACE_OPPORTUNITY_BRIEFING_CRON=45 8 * * 1-5
TENDERTRACE_FEISHU_TASK_SYNC_ENABLED=false
TENDERTRACE_FEISHU_TASK_SYNC_CRON=*/10 * * * *
TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED=false
TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_CRON=*/15 * * * *
TENDERTRACE_SOURCE_ALERT_ENABLED=false
TENDERTRACE_SOURCE_ALERT_CRON=15 */2 * * *
TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY=0.75
TENDERTRACE_SOURCE_ALERT_STALE_HOURS=24
TENDERTRACE_SOURCE_INCIDENT_SLA_HOURS=4

# 可选飞书消息/群聊接口。
FEISHU_ENABLED=false
FEISHU_BASE_URL=https://open.feishu.cn
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_DEFAULT_RECEIVE_ID=
FEISHU_DEFAULT_RECEIVE_ID_TYPE=chat_id
FEISHU_CALENDAR_ID=
FEISHU_CALLBACK_VERIFICATION_TOKEN=
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
python -m tendertrace feishu-import-leads --dry-run
python -m tendertrace feishu-import-leads
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
python -m tendertrace feishu-bot-listen
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
- `POST /api/integrations/feishu/bitable/import-leads`：预检或导入伙伴提交的多维表格线索。
- `GET /api/integrations/feishu/bitable/import-runs`：查看伙伴线索同步运行审计。
- `POST /api/outbox/{filename}/send-feishu`：上传并发送指定 Word 报告。
- `POST /api/memory/advice/{advice_id}/feedback`：采纳、完成或忽略动态建议；可执行建议会创建或复用后台采集/用户增量订阅，并把自动化结果写入反馈账本。
- `POST /api/memory/weekly/send-feishu`：发送最近一周的交互式使用与机会周报，可在卡片内处理建议。
- `POST /api/opportunities/send-feishu`：发送可操作机会卡片，并按需创建幂等任务与截止日程。
- `GET /api/opportunities/{notice_id}/workflow`：读取机会负责人、销售阶段和飞书协同状态。
- `GET /api/opportunities/{notice_id}/facts`：读取字段级核验结果与变更审计。
- `PATCH /api/opportunities/{notice_id}/facts`：提交带来源链接的核验事实，重算机会与准入，并回写飞书台账。
- `POST /api/opportunities/{notice_id}/actions`：执行带阶段、资格和重大变更复核门禁的认领、复核确认、Go/Hold/No-Go、投标准备、中标/失标与归档动作。
- `GET /api/opportunities/{notice_id}/team`：读取阶段感知的机会团队、伙伴、覆盖率和缺口。
- `POST /api/opportunities/{notice_id}/team`：幂等新增或更新团队成员，并同步飞书 Task 关注人与多维表格。
- `DELETE /api/opportunities/{notice_id}/team/{member_id}`：审计式移除团队成员，并撤销对应飞书 Task 关注人。
- `GET /api/opportunities/{notice_id}/stakeholders`：读取阶段感知的客户关键人、关系覆盖、健康度、风险与策略行动。
- `POST /api/opportunities/{notice_id}/stakeholders`：提交带来源证据的关键人事实并重算机会准入、策略及 Base 摘要。
- `DELETE /api/opportunities/{notice_id}/stakeholders/{stakeholder_id}`：审计式移除关键人并刷新关系风险。
- `GET /api/opportunities/changes`：读取公告修订账本，可按公告过滤。
- `POST /api/opportunities/changes/send-feishu`：向机会负责人聚合发送尚未成功投递的公告变更。
- `POST /api/opportunities/escalations/send-feishu`：发送决策超时与任务逾期的统一管理摘要；同一机会合并风险，并按每日风险集合去重。
- `POST /api/opportunities/briefing/send-feishu`：发送机会经营晨报，汇总机会池、负责人、资格、决策、市场和来源风险；自动任务按同日机会状态去重。
- `POST /api/integrations/feishu/callback`：接收卡片动作，校验令牌后推进机会状态或回写建议反馈，并同步相关业务状态。
- `POST /api/integrations/feishu/events`：接收飞书消息事件，校验令牌、去重后异步执行自然语言查询或创建订阅。
- `GET /api/integrations/feishu/message-events`：查看飞书会话指令的运行、订阅、失败与恢复审计。
- `GET /api/sources/alerts`：读取基于真实运行记录计算的来源 SLO 快照。
- `POST /api/sources/alerts/send-feishu`：把当前来源异常发送到飞书；非强制调用按当日状态指纹去重。
- `POST /api/sources/alerts/create-feishu-task`：为当前来源异常创建飞书处置任务；默认成员作为负责人，并按当日状态指纹去重。
- `GET /api/sources/incidents`：读取来源异常处置台账，不返回飞书任务标识。
- `POST /api/sources/incidents/sync`：回收飞书任务状态并重新验证实际来源 SLO，识别处理中、逾期、待关闭、核验失败和已解决。
- `GET /api/integrations/feishu/users`：仅返回应用通讯录授权范围内可分配的成员，不返回手机号、邮箱等敏感字段。

设置页的“飞书连接中心”可以从机器人已加入的会话中选择默认接收目标。立即运行或订阅勾选“同时发送飞书”后，生成的 Word 会自动投递；每次成功或失败都会记录时间、文件和错误原因。若平台返回 `232025`，需要先在应用后台启用机器人能力并发布新版本；若返回 `232034`，需要确认当前租户已经安装已发布应用。

机会协同使用公告 ID 生成任务 `client_token` 与日程 `idempotency_key`，重复同步不会重复创建任务或日程。启用截止日程需配置 `FEISHU_CALENDAR_ID`；启用卡片动作需配置 `FEISHU_CALLBACK_VERIFICATION_TOKEN`，并在飞书开发者后台把可公网访问的 `/api/integrations/feishu/callback` 注册为回调地址。本地 `127.0.0.1` 不能直接接收飞书云端回调。

机会经营晨报或单机会卡片中的“认领机会”会先通过本地状态图与资格门禁，再以点击者 `open_id` 创建并分派 Task v2；已有任务会直接复用并补充分派，不产生重复待办。响应与活动账本只保存创建/复用、分派和日程状态，不在自动化摘要中暴露任务或日程标识。

启用 `TENDERTRACE_FEISHU_TASK_SYNC_ENABLED` 后，Task v2 完成状态不仅会回写本地 workflow 与多维表格，还会向机会负责人发送阶段合法的下一步机会卡。系统不会把“完成跟进任务”误判为“机会已完成”，也不会绕过资格门禁自动推进阶段。完成通知按任务完成事件与接收人生成不可逆指纹并写入投递账本：失败会在下次同步重试，成功后不重复发送；没有负责人时才回退到统一飞书接收目标。

仍未完成的逾期任务会向负责人发送红色机会卡，展示当前阶段合法动作和证据门禁。逾期催办按“任务、接收人、本地日期”生成不可逆指纹，同一天只发送一次，发送失败仍可在后续同步重试；跨天持续逾期才再次提醒。中标、未中标或已归档机会不会继续催办。任务同步 API 与 Web 操作反馈分别返回完成跟进和逾期提醒的发送、跳过数量。

管理升级队列统一纳入决策 SLA 超时与飞书任务逾期。同一机会同时命中两类风险时合并为一行，Web 看板和飞书管理摘要分别展示风险类型、负责人、阶段、等待时长与截止时间。摘要按当天风险集合去重；纯决策升级继续沿用原有 `decision_sla` 指纹，不会因版本升级重复发送。发送结果返回机会数、决策超时数和任务逾期数。

机会页分配负责人时会读取飞书应用当前获授权的通讯录成员。应用需要开通通讯录基本信息读取权限并配置可访问的数据范围；选择成员后，新任务会直接设置 `assignee`，已有未指派任务会通过 Task v2 成员接口补充负责人，同时回写本地 workflow 与多维表格。通讯录不可用时界面会明确降级为仅记录负责人姓名，任务保持未指派，不会伪造成员绑定。

机会经营晨报默认关闭自动发送。设置 `TENDERTRACE_OPPORTUNITY_BRIEFING_ENABLED=true` 后，APScheduler 按 `TENDERTRACE_OPPORTUNITY_BRIEFING_CRON` 汇总本地真实机会与来源健康记录并投递到默认会话；Web 机会情报页也可手动触发。卡片中的认领、确认、Go 和投标准备动作复用同一套状态图、资格门禁和回调审计，不维护第二份流程状态。

来源健康自动告警默认关闭。设置 `TENDERTRACE_SOURCE_ALERT_ENABLED=true` 后，系统按 `TENDERTRACE_SOURCE_ALERT_CRON` 检查登录态、可靠度阈值和最近成功时间，并将异常来源发送到默认飞书接收目标。可靠度与新鲜度阈值分别由 `TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY` 和 `TENDERTRACE_SOURCE_ALERT_STALE_HOURS` 控制；未产生真实运行记录的来源保持“待观察”，不会因零样本误报。数据源页可把当前异常转成飞书 Task v2 处置任务，使用默认授权成员作为负责人，截止时间由 `TENDERTRACE_SOURCE_INCIDENT_SLA_HOURS` 控制；任务使用当日来源状态指纹作为幂等键。处置事件会持久化到本地，启用 `TENDERTRACE_FEISHU_TASK_SYNC_ENABLED` 后与销售机会任务共用同步周期；飞书任务完成但来源仍异常时保持打开，避免形式化关闭。

飞书任务状态支持双向回收。机会页的“同步任务状态”会读取已关联任务的完成时间与截止时间，识别进行中、已完成和已逾期状态，并幂等回写本地 workflow、审计事件和多维表格。设置 `TENDERTRACE_FEISHU_TASK_SYNC_ENABLED=true` 后，APScheduler 按 `TENDERTRACE_FEISHU_TASK_SYNC_CRON` 自动执行；启用前需为应用开通任务读取或任务读写权限。

机会公告变更提醒默认关闭。设置 `TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED=true` 后，APScheduler 按 `TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_CRON` 扫描未投递修订，将预算、截止时间、采购主体、正文和附件变化优先发给机会负责人。发送失败不会确认修订，下一轮继续重试；发送成功后同一修订不会重复提醒同一接收人。

重大变更复核不依赖提醒开关。对处于机会确认、策略制定或投标准备阶段的公告，合同边界类变化会写入 `notice_change_reviews`，复核时限由 `TENDERTRACE_CHANGE_REVIEW_SLA_HOURS` 控制。待复核期间其他销售动作被统一动作契约阻断；原决策不会在复核后自动恢复，负责人必须基于最新公告重新完成决策。飞书变更卡可直接确认复核，多维表格记录视图会显示同一待办和复核说明输入框。

飞书会话也可以直接作为 TenderTrace 的自然语言入口。为自建应用启用机器人能力并订阅 `im.message.receive_v1` 与 `card.action.trigger` 后，安装可选依赖 `python -m pip install -e .[feishu]`，运行 `python -m tendertrace feishu-bot-listen` 即可通过官方长连接接收消息和机会卡片动作，无需把本地服务暴露到公网。即时问题会运行检索、生成 Word 并回传原会话；带发送时间或频率的问题会创建绑定原会话的增量订阅。事件先写入 `feishu_message_events`，以 `event_id` 和 `message_id` 双重去重，进程重启时会恢复未处理或超时任务。启用 `TENDERTRACE_SCHEDULER_ENABLED` 时，该 CLI 同时承担订阅调度；同一数据库只能运行一个启用调度器的进程。

生产环境也可使用未加密的 HTTP 事件订阅：配置 `FEISHU_CALLBACK_VERIFICATION_TOKEN`，将可公网访问的 `/api/integrations/feishu/events` 设置为请求地址。该入口只接受令牌校验通过的事件并立即返回，实际检索在线程池执行。需要事件加密时应使用已经支持加密处理的官方长连接模式。长连接和 HTTP 回调只选择一种，避免同一事件产生无意义的重复投递；即使同时收到，持久化幂等键也会阻止重复运行。

多维表格服务端同步还需要具体 Base 文档的 `app_token` 与数据表的 `table_id`。二者可以从实际多维表格 URL 获取，不能使用应用 App ID 或记录视图的 `blk_...` BlockTypeID 替代：

```env
TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=
TENDERTRACE_FEISHU_BITABLE_TABLE_ID=
TENDERTRACE_FEISHU_BITABLE_BASE_URL=
```

记录视图插件位于 `integrations/feishu-record-view/`，已配置 App ID 与 BlockTypeID，未包含任何密钥。安装官方 CLI 后先执行 `opdev login`，再进入 `opportunity-view` 执行 `npm install` 和 `npm run start`。本地调试必须在 `block.json` 增加实际 Base 文档 URL；生产构建可直接执行 `npm run build`。插件先调用 `/api/opportunities/analyze` 生成当前行研判；存在公告ID时继续读取 `/api/opportunities/{notice_id}/facts`，以本地库中的负责人、阶段、资格、决策与任务状态覆盖非权威展示。核验动作仍通过事实 API 幂等重算；工作流动作通过统一阶段门禁执行并同步台账。Base 用户标识只用于审计，首次认领必须发送机会卡，由点击成员的真实 `open_id` 建立负责人和 Task v2 关系。

配置 `TENDERTRACE_FEISHU_BITABLE_BASE_URL` 后，机会情报页和设置页会提供飞书台账直达入口；连接中心展示的线索数仅统计含项目指纹或公告 ID 的 TenderTrace 业务记录，不包含飞书默认空白行。

合作伙伴线索使用同一张多维表格：填写“标题”“来源链接”，可选填写“线索正文”“伙伴提交人”“地区”“采购人”和附件链接，再把“状态”设为“伙伴提交”或“待导入”。设置页“导入伙伴线索”会先执行预检，用户确认后才入库；CLI 可用 `feishu-import-leads --dry-run` 执行同样的审计。系统只访问公网 HTTP/HTTPS 地址，拒绝本机、私网、云元数据地址、带凭据 URL 和转向这些地址的重定向；响应受大小上限约束。核验结果会回写“来源核验”“核验时间”“核验摘要”，并直接影响机会可信度评分。

需要自动轮询时，设置 `TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=true` 并通过 `TENDERTRACE_FEISHU_LEAD_IMPORT_CRON` 指定频率。该开关默认关闭，且凭据不完整时应用会拒绝启动。手动预检、手动导入和定时导入均写入 `feishu_lead_import_runs`，可通过 `GET /api/integrations/feishu/bitable/import-runs` 查看扫描、候选、导入、核验成功、核验失败、不安全地址、跳过与耗时。

抓取器的 HTTP/动态浏览器分层、资源拦截、退避和恢复策略参考了 [Scrapling](https://github.com/D4Vinci/Scrapling) 的公开设计；TenderTrace 未复制其实现，也未引入 Patchright、curl-cffi 等额外运行时依赖。

## Web 工作台

Web UI 覆盖以下视图：

- 工作台：输入自然语言问题，选择立即运行或订阅以及 Web/飞书交付；模型策略和搜索深度收纳在高级设置中。
- 历史运行：查看 run 记录、trace、checkpoint 和报告路径。
- 订阅管理：管理用户定时报告订阅，查看新增/跳过历史、下次触发时间和最近 Word。
- 数据源：查看公开源、千里马登录态、入口路由、发现规则，以及命中率、延迟和可靠性等来源健康指标。
- Agent 评测：分开展示人工金标用例与意图 Harness；金标完整后才给出严格 Recall 验收状态。
- 用户记忆：查看使用画像、知识偏好、风险信号和生成式行动建议。
- 机会情报：按行动优先、截止时间或发布时间排序，查看待认领/临期队列和市场基准，在详情弹窗中研判竞争者、需求覆盖、证据边界、风险与角色行动，并可发送经营晨报。
- 设置：查看运行配置，以及飞书报告、台账、机会卡片、经营晨报、任务、截止日程、状态回调和智能体能力矩阵。

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

- Current stage: P47
- 321 automated tests pass, including 426 subtests.
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
- Twelve-source collection from Chinese procurement platforms, a Qianlima login-state source, TED, UNGM, World Bank, Asian Development Bank, African Development Bank, EBRD ECEPP, Inter-American Development Bank, and the official UK Contracts Finder / Find a Tender APIs. UNGM adds procurement coverage across 32 UN organizations.
- Scope-aware routing that keeps domestic queries on domestic sources and activates the matching UK, EU, World Bank, IDB, or global sources only when requested.
- Managed fetching with `Retry-After`, exponential backoff, block detection, HTTP-first execution, resource-light Playwright recovery, and traceable fetch statistics.
- Login-state vault based on Playwright `storage_state`; credentials are never stored in code. Member search submits the actual topic and treats same-origin API authentication failures as `login_expired` instead of silently returning zero results.
- Local-first retrieval with SQLite FTS5, jieba tokenization, and BM25 ranking.
- Background ingest subscriptions separated from user report subscriptions, with normalized pools and deterministic identity to prevent duplicate collection plans.
- Incremental scheduled delivery with `sent_history` deduplication.
- Optional SMTP email delivery for generated Word reports.
- Optional Feishu Bitable opportunity ledger for incremental tender records.
- Bidirectional Feishu partner-lead ingestion: approved Bitable rows are validated against their public source, stored with a content hash and evidence excerpt, indexed in FTS, and written back with idempotent import and verification status.
- Feishu opportunity collaboration with interactive cards, idempotent owner tasks, bid-deadline calendar events, HTTP or official long-connection card callbacks, and an auditable local event stream. Claiming creates or reuses Task v2 and assigns the clicking member; completion sends a stage-valid follow-up card, while overdue tasks produce a daily owner reminder until resolved or the opportunity becomes terminal.
- A unified Feishu delivery target picker that combines bot-visible chats and authorized directory members; reports, weekly digests, operations briefings, and source alerts reuse the selected target.
- Native Feishu conversation commands: immediate natural-language questions return Word to the originating chat, while scheduled questions create chat-bound incremental subscriptions with durable deduplication and recovery.
- Evidence-led opportunity grading with freshness, completeness, credibility, readiness, risks, and role-specific actions.
- Stage-aware opportunity-team governance with one accountable owner plus solution, commercial, delivery, legal, and partner roles. Coverage gaps are persisted, audited, and included in the Go qualification gate.
- Feishu Task v2 collaboration that keeps the owner as `assignee` and synchronizes internal or partner team members as `follower`; Bitable stores the team roster, partner organizations, coverage, and missing roles.
- Evidence-backed stakeholder intelligence for economic and technical buyers, procurement contacts, champions, end users, and blockers. It tracks influence, stance, relationship strength, accountable team member, next action, and provenance without collecting phone numbers or email addresses.
- Stage-aware account strategy that scores relationship coverage and health, detects high-influence resistance and unknown positions, derives actions from observed gaps, and feeds the same Go gate used by Web and Feishu.
- Auditable fact verification for purchaser, project number, budget, deadline, and region. Evidence-backed overlays preserve the raw notice, recompute opportunity quality and qualification gates, and synchronize the resulting fields to Feishu Bitable.
- Configurable sales qualification gates covering ownership, purchaser identity, credibility, completeness, deadline viability, opportunity score, requirement coverage, team coverage, and stakeholder coverage. Stage transitions are rejected until workflow, evidence, staffing, and customer-relationship requirements pass.
- Durable Go/Hold/No-Go decisions with actor, rationale, and timestamp synchronized across SQLite, Web, shared Feishu cards, and Bitable. Decision SLA breaches and overdue Task v2 work merge into one opportunity-level management queue and a deduplicated Feishu summary.
- Actionable Feishu opportunity briefings that combine grade, owner gaps, qualification gates, deadlines, decision SLA, market signals, and source health, with weekday automation, receiver-scoped daily deduplication, and in-card workflow actions.
- A source SLO workflow derived from login state, observed reliability, and last-success freshness, with deduplicated alerts, Task v2 incidents, owner assignment, a configurable SLA, and evidence-based closure only after both task completion and real source recovery.
- Action queue sorting driven by opportunity grade, missing ownership, and bid deadlines, with unowned priority, due-soon, and active-collaboration counters.
- Per-source observability for real attempts, correct routing skips, run hit rate, request success, latency, and reliability.
- Evidence-grade source trust that combines source authority, observed collection reliability, grounded snapshots, independent-source corroboration, and attachment evidence. Zero-run sources remain explicitly unobserved, while low trust feeds the same sales qualification gate used by Web and Feishu.
- Local market benchmarks from the latest 500 notices, including comparable-category budgets, purchaser concentration, and procurement-stage distribution; insufficient samples are surfaced explicitly.
- Competition intelligence extracted from result and contract notices, including awarded suppliers, amounts, evidence excerpts, and comparable-category supplier history.
- An eight-dimension requirement review covering specifications, integration, delivery, acceptance, service, qualifications, scoring, and security; missing evidence is explicitly labeled for verification.
- A Feishu record-view workflow portal that reloads authoritative ownership, stage, qualification, decision, and task state as the selected row changes; it writes intelligence, verifies evidence-backed facts, and executes stage-valid actions through the same auditable gates as the Web UI. Initial claiming remains an interactive-card action so a Base user identifier is never mistaken for the member `open_id` required by Task v2.
- A versioned, server-driven action contract that derives labels, intent, availability, gate reasons, decision input, and identity requirements from the workflow domain. Web, interactive Feishu cards, and the record-view extension consume the same contract instead of duplicating stage branches.
- A durable notice-revision ledger backed by in-place UPSERT semantics. Reingestion preserves workflow ownership, verified facts, audit events, and original creation time while tracking meaningful changes to deadlines, budgets, content, and attachments.
- Receiver-scoped Feishu change alerts grouped by opportunity owner, with retryable failures, irreversible successful-delivery deduplication, terminal-stage suppression, and a configured-target fallback only for unowned opportunities.
- Material-change governance for active opportunities. Contract-boundary changes create a review ledger, invalidate stale Go/Hold decisions, block downstream actions through the shared action contract, and restart the decision SLA only after an accountable Web, Feishu card, or record-view acknowledgement. Overdue reviews join the existing management escalation queue.
- Text cleaning, URL canonicalization, project-number extraction, SimHash clustering.
- Bounded attachment download and extraction for PDF, DOCX, and XLSX.
- Evidence chain with source links, excerpts, attachment snapshots, and fact checks.
- Word report generation with title, publish time, source link, core content, and attachment links.
- Rule-only, local Ollama, and OpenAI-compatible cloud model enhancement modes.
- Agent evaluation covering RAG, agent execution, intent harness, recall proxy, and gold Recall@K; evaluation stays incomplete until the manual gold set is fully annotated.
- User memory knowledge base that records queries, clicks, downloads, subscriptions, and runs, then converts accepted topic/region advice into idempotent APScheduler ingestion plans and accepted high-frequency queries into daily 09:00 incremental user subscriptions.
- Accepted A-grade follow-up and B-grade qualification advice sends a real opportunity briefing. Feishu card actions bind it to the current chat, Web actions use the configured collaboration target, and the delivery ledger deduplicates each receiver independently.
- Feishu-origin subscriptions bind to the card's current chat and deliver only new notices through `sent_history`; the same query, schedule, channels, and receiver reuse one semantic subscription.
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
  source_trust.py        # Source authority, observed reliability, and evidence trust
  retrieval.py           # FTS5 / LIKE / vector-fused retrieval
  workflow.py            # Opportunity stages, owners, Feishu IDs, and action audit
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
FEISHU_CALENDAR_ID=
FEISHU_CALLBACK_VERIFICATION_TOKEN=

# Optional Feishu Bitable partner-lead ingestion.
TENDERTRACE_FEISHU_APP_ID=
TENDERTRACE_FEISHU_APP_SECRET=
TENDERTRACE_FEISHU_BITABLE_APP_TOKEN=
TENDERTRACE_FEISHU_BITABLE_TABLE_ID=
TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=false
TENDERTRACE_FEISHU_LEAD_IMPORT_CRON=*/15 * * * *

# Sales qualification thresholds and management decision SLA.
TENDERTRACE_QUALIFICATION_MIN_OPPORTUNITY_SCORE=65
TENDERTRACE_QUALIFICATION_MIN_CREDIBILITY=60
TENDERTRACE_QUALIFICATION_MIN_COMPLETENESS=55
TENDERTRACE_QUALIFICATION_MIN_REQUIREMENT_COVERAGE=40
TENDERTRACE_QUALIFICATION_MIN_TEAM_COVERAGE=60
TENDERTRACE_QUALIFICATION_MIN_STAKEHOLDER_COVERAGE=50
TENDERTRACE_DECISION_SLA_HOURS=24
TENDERTRACE_CHANGE_REVIEW_SLA_HOURS=8
TENDERTRACE_OPPORTUNITY_ESCALATION_ENABLED=false
TENDERTRACE_OPPORTUNITY_ESCALATION_CRON=0 9,14 * * 1-5
TENDERTRACE_OPPORTUNITY_BRIEFING_ENABLED=false
TENDERTRACE_OPPORTUNITY_BRIEFING_CRON=45 8 * * 1-5
TENDERTRACE_FEISHU_TASK_SYNC_ENABLED=false
TENDERTRACE_FEISHU_TASK_SYNC_CRON=*/10 * * * *
TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED=false
TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_CRON=*/15 * * * *
TENDERTRACE_SOURCE_ALERT_ENABLED=false
TENDERTRACE_SOURCE_ALERT_CRON=15 */2 * * *
TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY=0.75
TENDERTRACE_SOURCE_ALERT_STALE_HOURS=24
TENDERTRACE_SOURCE_INCIDENT_SLA_HOURS=4
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
python -m tendertrace feishu-bot-listen
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
- `POST /api/integrations/feishu/bitable/import-leads`: preview or import partner-submitted Bitable leads.
- `GET /api/integrations/feishu/bitable/import-runs`: inspect partner-lead synchronization audits.
- `POST /api/outbox/{filename}/send-feishu`: upload and send a Word report.
- `POST /api/memory/advice/{advice_id}/feedback`: accept, complete, or dismiss a dynamic recommendation and persist that decision in the memory ledger.
- `POST /api/memory/weekly/send-feishu`: send an interactive weekly usage and opportunity card whose recommendations can be actioned in Feishu.
- `POST /api/opportunities/send-feishu`: send an actionable opportunity card and optionally create an idempotent task and deadline event.
- `GET /api/opportunities/{notice_id}/workflow`: inspect the owner, sales stage, and Feishu artifact state.
- `GET /api/opportunities/{notice_id}/facts`: inspect field-level verified facts and their audit history.
- `PATCH /api/opportunities/{notice_id}/facts`: submit evidence-backed facts, recompute qualification, and synchronize the Bitable record.
- `POST /api/opportunities/{notice_id}/actions`: execute claim, material-change acknowledgement, pursuit, Go/Hold/No-Go, bid preparation, outcome, and archive actions through shared stage, qualification, and review gates.
- `GET /api/opportunities/{notice_id}/team`: inspect the stage-aware team roster, partners, coverage, and missing roles.
- `POST /api/opportunities/{notice_id}/team`: idempotently add or update a member and synchronize Task followers and Bitable.
- `DELETE /api/opportunities/{notice_id}/team/{member_id}`: audit a member removal and remove the matching Task follower.
- `GET /api/opportunities/{notice_id}/stakeholders`: inspect stage-aware stakeholders, relationship coverage, health, risks, and strategy actions.
- `POST /api/opportunities/{notice_id}/stakeholders`: persist an evidence-backed stakeholder and recompute qualification, strategy, and the Bitable summary.
- `DELETE /api/opportunities/{notice_id}/stakeholders/{stakeholder_id}`: audit stakeholder removal and refresh relationship risk.
- `GET /api/opportunities/changes`: inspect the durable notice-revision ledger, optionally filtered by notice.
- `POST /api/opportunities/changes/send-feishu`: deliver pending notice changes to opportunity owners without duplicating successful deliveries.
- `POST /api/opportunities/escalations/send-feishu`: send a unified decision-overdue and task-overdue management summary, merging risks per opportunity and deduplicating the daily risk set.
- `POST /api/opportunities/briefing/send-feishu`: send an opportunity operations briefing that combines pipeline, ownership, qualification, decision, market, and source-risk context.
- `POST /api/integrations/feishu/callback`: verify card callbacks, then advance opportunity state or persist recommendation feedback through the shared business workflow.
- `POST /api/integrations/feishu/events`: verify, deduplicate, and asynchronously execute inbound Feishu text commands.
- `GET /api/sources/alerts`: inspect the source SLO snapshot computed from observed runs.
- `POST /api/sources/alerts/send-feishu`: send current source issues to Feishu, deduplicated by daily state unless forced.
- `POST /api/sources/alerts/create-feishu-task`: create an idempotent Task v2 incident for current source issues and assign the configured member when available.
- `GET /api/sources/incidents`: list the local source-incident ledger without exposing Feishu task identifiers.
- `POST /api/sources/incidents/sync`: synchronize Task v2 state and re-evaluate the affected sources before resolving an incident.
- `GET /api/integrations/feishu/message-events`: inspect inbound run, subscription, failure, and recovery audits.
- `GET /api/integrations/feishu/users`: list only assignable users inside the app's authorized contact scope; mobile numbers and email addresses are not returned.

The Feishu connection center can select a default chat from the bot's visible chats. Queries and subscriptions can opt into automatic Word delivery, while every success or failure is written to the local delivery ledger. Error `232025` means bot capability must be enabled and a new app version published; error `232034` means the published app is not installed in the current tenant.

Task `client_token` and calendar `idempotency_key` values are derived from the notice ID, so repeated synchronization does not duplicate those artifacts. Set `FEISHU_CALENDAR_ID` to enable deadline events. Set `FEISHU_CALLBACK_VERIFICATION_TOKEN` and register the publicly reachable `/api/integrations/feishu/callback` endpoint in Feishu Developer Console to enable card actions; a local `127.0.0.1` URL is not reachable from Feishu Cloud.

The Claim action first passes the shared workflow and qualification gates, then creates or reuses Task v2 with the clicking member's `open_id` as assignee. Existing tasks are assigned instead of duplicated. Automation summaries expose only created/reused, assignment, and calendar status, without returning task or event identifiers.

When `TENDERTRACE_FEISHU_TASK_SYNC_ENABLED` is enabled, a completed Task v2 is synchronized to the local workflow and Bitable, then produces a stage-valid follow-up card for the opportunity owner. Completing a follow-up task never closes the opportunity or bypasses qualification gates. Delivery uses an irreversible, receiver-scoped completion fingerprint: failed sends retry during the next synchronization, successful sends are not duplicated, and the shared Feishu target is used only when no owner is available.

An incomplete overdue task produces a red, stage-valid card for its owner. Its irreversible fingerprint is scoped by task, receiver, and local date, so repeated synchronization sends at most one reminder per day, failed delivery remains retryable, and a task that is still overdue on a later date can be raised again. Won, lost, and archived opportunities remain silent. The task-sync API and Web feedback expose sent and skipped counts for completion follow-ups and overdue reminders separately.

The management escalation queue combines decision-SLA breaches and overdue Feishu tasks. When both affect the same opportunity, Web and Feishu show one row with both issue types, owner, stage, wait time, and deadline. Daily delivery deduplicates the complete risk set; decision-only sets retain the legacy `decision_sla` fingerprint to prevent upgrade-time duplicates. Results expose opportunity, decision, and task counts separately.

The Opportunity view resolves owners from the Feishu app's authorized contact scope. Grant basic contact read permission and configure the app's contact data scope. A selected member becomes the task `assignee`; an existing unassigned Task v2 task receives the member without creating a duplicate, and the owner is synchronized to the local workflow and Bitable. If the directory is unavailable, the UI explicitly falls back to recording the owner's name only and leaves the task unassigned.

Scheduled opportunity briefings are disabled by default. Set `TENDERTRACE_OPPORTUNITY_BRIEFING_ENABLED=true` and configure `TENDERTRACE_OPPORTUNITY_BRIEFING_CRON` to deliver a state-deduplicated weekday briefing to the default chat. The Web Opportunity Intelligence view can also trigger it manually. Claim, qualify, Go, and bid-preparation buttons reuse the same workflow graph, qualification gates, callback handler, and audit stream as the Web UI.

Feishu task status can be synchronized back into TenderTrace. The Opportunity Intelligence view reads completion and due timestamps for linked tasks, classifies them as open, completed, or overdue, and idempotently updates the local workflow, audit ledger, and Bitable record. Enable scheduled synchronization with `TENDERTRACE_FEISHU_TASK_SYNC_ENABLED=true` and `TENDERTRACE_FEISHU_TASK_SYNC_CRON`; the Feishu app needs task read or task write permission.

Opportunity notice-change alerts are disabled by default. Set `TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_ENABLED=true` to scan pending revisions on `TENDERTRACE_OPPORTUNITY_CHANGE_ALERT_CRON`. Deadline, budget, purchaser, content, and attachment changes are grouped by owner. Failed delivery remains retryable; successful delivery is deduplicated per revision and receiver, and terminal opportunities stay silent.

Material-change reviews are independent of the delivery switch. Contract-boundary changes on qualifying, pursuing, or bidding opportunities are persisted in `notice_change_reviews`; `TENDERTRACE_CHANGE_REVIEW_SLA_HOURS` controls their due time. The shared action contract blocks other sales transitions while a review is pending. Acknowledgement from Web, an interactive Feishu card, or the Bitable record view restarts decision timing without restoring the stale decision. Overdue reviews are merged into the existing management escalation.

Automated source-health delivery is disabled by default. Set `TENDERTRACE_SOURCE_ALERT_ENABLED=true` to evaluate login state, observed reliability, and last-success freshness on `TENDERTRACE_SOURCE_ALERT_CRON`. The reliability and freshness thresholds are controlled by `TENDERTRACE_SOURCE_ALERT_MIN_RELIABILITY` and `TENDERTRACE_SOURCE_ALERT_STALE_HOURS`. Sources without observed runs remain pending and do not generate zero-sample alerts. The Data Sources view can convert current issues into a Feishu Task v2 incident, assign the configured authorized member, and set its deadline from `TENDERTRACE_SOURCE_INCIDENT_SLA_HOURS`; the daily source-state fingerprint prevents duplicate tasks. Incidents are persisted locally and reuse `TENDERTRACE_FEISHU_TASK_SYNC_ENABLED` for periodic synchronization. Completing a task does not resolve the incident while its source still violates the SLO.

Feishu conversations can also be the native natural-language entry point. Enable the bot capability, subscribe to `im.message.receive_v1`, install the optional dependency with `python -m pip install -e .[feishu]`, then run `python -m tendertrace feishu-bot-listen`. The official long connection does not require exposing the local service. Immediate questions run retrieval, generate Word, and deliver it to the originating chat; questions containing a delivery time or cadence create an incremental subscription bound to that chat. Every event is persisted and deduplicated by both event and message ID, and unfinished or stale work is recovered after restart. When `TENDERTRACE_SCHEDULER_ENABLED` is enabled, this CLI also owns subscription scheduling; only one scheduler-enabled process may use a given database.

For unencrypted production HTTP event delivery, configure `FEISHU_CALLBACK_VERIFICATION_TOKEN` and register the publicly reachable `/api/integrations/feishu/events` URL. The endpoint acknowledges verified events immediately and executes work in a bounded thread pool. Use the official long connection when encrypted event transport is required. Use either long connection or HTTP delivery; the durable idempotency ledger still prevents duplicate execution if both transports receive the same event.

Server-side Bitable sync also requires the target Base document's `app_token` and table `table_id`. Extract both from the actual Base URL; neither the application App ID nor the record-view `blk_...` BlockTypeID can replace them.

The record-view extension lives in `integrations/feishu-record-view/`. Its App ID and BlockTypeID are committed, while credentials are not. Run `opdev login`, then `npm install` and `npm run start` under `opportunity-view`. Local debugging requires an actual Base document URL in `block.json`; production assets build with `npm run build`. The extension combines row-level analysis with authoritative local workflow, qualification, decision, and task state. It writes intelligence, submits idempotent fact verification, and runs stage-valid workflow actions through the shared API. Base identity is audit-only: initial claim is deliberately routed through an interactive opportunity card so the clicking member's real `open_id` can own Task v2 work.

When `TENDERTRACE_FEISHU_BITABLE_BASE_URL` is configured, the Opportunity Intelligence and Settings views expose a direct Base link. The synced lead count excludes Feishu's default blank rows and counts only TenderTrace records with a project fingerprint or notice ID.

For partner-submitted intelligence, fill `标题` and `来源链接`, optionally add `线索正文`, `伙伴提交人`, region, buyer, and attachment links, then set `状态` to `伙伴提交` or `待导入`. The Settings action verifies the source during preview and imports only after confirmation. The same workflow is available through `python -m tendertrace feishu-import-leads --dry-run` and `python -m tendertrace feishu-import-leads`. Only public HTTP/HTTPS destinations are fetched; localhost, private networks, metadata addresses, credential-bearing URLs, and redirects to them are rejected. Verification writes `来源核验`, `核验时间`, and `核验摘要` back to Bitable and directly affects opportunity credibility.

Set `TENDERTRACE_FEISHU_LEAD_IMPORT_ENABLED=true` to poll approved rows automatically and configure the cadence with `TENDERTRACE_FEISHU_LEAD_IMPORT_CRON`. Automation is disabled by default, and startup fails when it is enabled without complete Bitable credentials. Preview, manual import, and scheduled runs are recorded in `feishu_lead_import_runs`; `GET /api/integrations/feishu/bitable/import-runs` exposes scan, candidate, import, verification, unsafe URL, skip, failure, and duration metrics.

The managed fetcher adopts public architectural ideas from [Scrapling](https://github.com/D4Vinci/Scrapling), including HTTP/dynamic tiers, resource control, backoff, and recovery. TenderTrace does not copy Scrapling's implementation or require its Patchright/curl-cffi runtime stack.

## Web Workbench

The Web UI includes:

- Workbench: enter natural-language queries, choose immediate or scheduled execution, and select Web/Feishu delivery; model and retrieval controls stay under advanced settings.
- Run history: inspect runs, trace events, checkpoints, and report paths.
- Subscription management: manage scheduled user report subscriptions.
- Data sources: inspect public sources and Qianlima login-state status.
- Agent evaluation: inspect RAG, agent, harness, recall, gold-set metrics, and vector coverage.
- User memory: inspect usage profiles, knowledge preferences, risk signals, and generated next-step advice.
- Opportunity intelligence: filter by procurement category and grade, inspect market benchmarks, open detailed evidence and competition reviews, and send the management briefing.
- Settings: inspect runtime plus Feishu report, Bitable, opportunity card, operations briefing, task, deadline calendar, callback, and agent readiness.

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

- Current stage: P47
- 321 automated tests pass, including 426 subtests.
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
