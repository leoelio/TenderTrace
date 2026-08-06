# P4 Web 工作台

## 目标

P4 实现可操作的 Web UI：用户可以在浏览器输入自然语言问题，触发公开源采集，查看运行状态、事件流、检查点，并下载 outbox 中的 Word 报告。

本阶段不引入前端构建链，采用 FastAPI 静态挂载 `web/dist`。这样部署和演示成本最低，也避免 UI 与后端 API 契约脱节。

## 新增模块

- `tendertrace/runner.py`：封装一次 `intent -> collect -> report` 运行，供 CLI、API 和未来定时器复用。
- `POST /api/runs`：同步触发一次采集并返回运行结果。
- `GET /api/runs/{run_id}`：查询运行台账。
- `web/dist/index.html`：工作台页面结构。
- `web/dist/styles.css`：响应式布局和视觉样式。
- `web/dist/app.js`：调用 API、刷新 outbox、渲染 trace/checkpoint。

## 启动

如果 8000 未占用：

```powershell
python -m tendertrace serve
```

如果 8000 已占用：

```powershell
$env:TENDERTRACE_PORT='8001'
python -m tendertrace serve
```

访问：

```text
http://127.0.0.1:8001/
```

## UI 工作流

1. 输入自然语言问题。
2. 设置最大翻页数和最大结果数。
3. 点击 `运行采集`。
4. 等待状态从运行中变为已完成。
5. 查看结果数、trace 事件数和三个检查点。
6. 在 outbox 表格中下载 Word 报告。
7. 点击某条 outbox 的追踪按钮，切换到该 run_id 的事件流。

## API 契约

触发运行：

```http
POST /api/runs
Content-Type: application/json

{
  "query": "最近36个月的上海区域内的设备招标信息都有哪些",
  "max_pages": 2,
  "max_results": 5
}
```

返回：

```json
{
  "run_id": "a680b879-af99-44de-a0b5-726f7e4dbe9b",
  "status": "finished",
  "notice_count": 3,
  "docx_path": "D:\\超聚变\\outputs\\最近36个月的上海区域内的设备招标信息都有哪些_202607061031.docx",
  "outbox_path": "D:\\超聚变\\outbox\\最近36个月的上海区域内的设备招标信息都有哪些_202607061031.docx",
  "trace_events": 10
}
```

## 验证结果

命令验证：

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
```

当前结果：

- 单元测试：27 个通过。
- Ruff：通过。
- Playwright 桌面验证：页面加载、点击运行、状态完成、`notice_count = 3`、trace 10 条、checkpoint 3 条、outbox 下载入口可见。
- Playwright 移动端验证：390px 视口无横向溢出，`scrollWidth = 390`。
- 控制台：无 error/warning。

Browser 插件当前未提供可用 in-app browser 后端，验证使用 Playwright fallback。

## 已知边界

- `POST /api/runs` 当前为同步运行，真实采集会阻塞请求数秒。后续定时/队列阶段会改成后台任务。
- UI 当前只展示公开源立即运行链路；订阅管理、登录站登录态和增量推送属于后续阶段。
- 8000 已被本机其他进程占用时，使用 8001 运行本阶段服务。
