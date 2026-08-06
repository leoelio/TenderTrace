# P21 导航工作台删除与 Agent 评测

## 目标

本阶段把 Web UI 从单页工具面板升级为更接近真实产品的工作台，并补齐三类能力：

1. 顶部导航：工作台、历史运行、订阅管理、数据源、Agent评测、设置。
2. 记录删除：支持删除 outbox Word 文件、删除运行记录、删除订阅任务。
3. Agent 评测：系统化展示 RAG、Agent、Harness、召回覆盖等指标。

删除功能只做用户明确触发的操作，不在页面刷新或评测时自动清理数据。

## 实现变更

### Web 导航与视觉

涉及文件：

- `web/dist/index.html`
- `web/dist/styles.css`
- `web/dist/app.js`
- `web/dist/logo.svg`

页面使用用户提供的 TenderTrace 图标作为品牌标识。顶栏保持桌面单行布局，普通 1280px 宽度下仍展示横向导航。

工作台保留自然语言输入、模型策略、搜索深度、订阅创建、运行进度、数据源状态、模型医生、报告输出和底部表格。

### 删除接口

涉及文件：

- `tendertrace/app/api.py`
- `tests/test_api_outbox.py`
- `tests/test_api_runs.py`
- `tests/test_api_subscriptions.py`

新增接口：

```text
DELETE /api/outbox/{filename}
DELETE /api/runs/{run_id}
DELETE /api/subscriptions/{subscription_id}
```

行为约束：

- 删除 outbox 会删除 `.docx` 文件和 `outbox_messages` 记录。
- 删除运行记录会把 run 标记为 `deleted` 并从历史列表隐藏，同时清理 trace、checkpoint、model_audits、outbox_messages 的展示关联；`sent_history` 会保留，避免订阅增量去重失效。
- 删除订阅会把订阅标记为 `deleted`，并尝试移除调度器里的对应 job。

### Agent 评测接口

涉及文件：

- `tendertrace/evaluation.py`
- `tendertrace/app/api.py`
- `tests/test_api_runs.py`

新增接口：

```text
GET /api/evaluations/agent
```

返回结构包含：

- `summary`：运行数、完成数、失败数、模型审计数、评测用例数。
- `rag`：证据通过率、证据检查量、附件抽取率、报告产出率。
- `agent`：checkpoint 完成率、平均 trace 事件数、失败率、模型审计数。
- `harness`：固定自然语言用例的 BidQL 字段准确率。
- `recall`：来源覆盖、去重保留、多源命中和可运行召回代理分。

当前 `recall_proxy` 是可运行近似指标，不声明为严格召回率。严格召回率需要人工标注全集。

## 验证

命令验证：

```powershell
node --check web\dist\app.js
python -m unittest discover -s tests -v
python -m ruff check tendertrace tests
```

当前结果：

- 89 个单元测试通过。
- Ruff 通过。
- 浏览器验证无 console error。
- 1280px 桌面宽度下顶栏保持单行。
- Agent评测页展示 5 个 summary tile、4 个指标卡、4 条 harness case 和 3 条说明。

浏览器验证地址示例：

```text
http://127.0.0.1:8011/
```

验证点：

1. 点击顶部 `Agent评测`，能看到 RAG、Agent、Harness、召回覆盖四个指标区。
2. 点击 `历史运行`，能看到运行记录、删除记录按钮、事件流和检查点面板。
3. 点击 `订阅管理`，能看到订阅删除按钮。
4. 工作台 outbox 表格能看到 Word 删除按钮。

## 注意事项

真实工作区里的删除按钮会改变本地数据库或 outbox 文件。自动化浏览器验证只确认按钮存在，不点击真实记录的删除按钮。删除运行记录不会清空 `sent_history`，因此不会让已推送内容重新进入订阅增量结果。
