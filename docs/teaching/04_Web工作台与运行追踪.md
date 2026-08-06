# 04 Web 工作台与运行追踪

## 本阶段解决什么问题

P4 把命令行能力变成可演示、可验证的浏览器工作流。用户不需要打开终端，也能完成输入问题、触发采集、下载 Word、查看运行追踪。

关键原则是：前端不硬编码结果。页面上的 outbox、trace、checkpoint 都来自 FastAPI 和 SQLite。

## 源码地图

- `tendertrace/runner.py`：一次运行的服务层。
- `tendertrace/cli.py`：CLI 调用 `runner.run_once()`。
- `tendertrace/app/api.py`：Web API 调用同一个 `runner.run_once()`。
- `web/dist/index.html`：页面骨架。
- `web/dist/styles.css`：三栏桌面布局和移动端单栏布局。
- `web/dist/app.js`：浏览器端状态管理和 API 调用。
- `tests/test_runner.py`：用假适配器验证服务层，不访问真实网站。
- `tests/test_api_runs.py`：验证运行 API。
- `tests/test_web_static.py`：验证静态工作台引用真实 API。

## 为什么抽出 runner.py

P3 的 `run-once` 最初写在 CLI 里。P4 如果直接在 API 里复制一份，会出现两个问题：

1. CLI 和 Web 的行为可能慢慢不一致。
2. 后续定时任务还要复制第三份。

所以 P4 新增 `runner.py`：

```python
def run_once(
    *,
    settings: Settings,
    query: str,
    now: datetime | None = None,
    max_pages: int = 1,
    max_results: int = 10,
    adapter: NoticeAdapter | None = None,
) -> RunOnceResult:
```

这个函数是当前“立即运行”的唯一入口。CLI、API、未来调度器都应该调用它。

## 服务层如何运行图

`run_once()` 内部仍然使用 P1 的 TenderGraph：

```text
intent -> collect -> report
```

区别是现在它负责完整的外层事务：

- 初始化数据库。
- 编译 BidQL。
- 写入 `runs`。
- 订阅 trace store。
- 保存 checkpoint。
- 生成 Word。
- 复制到 outbox。
- 写入 `outbox_messages`。
- 结束时更新 `runs.stats_json`。

这让 API 返回值和数据库追踪天然一致。

## 为什么测试使用假适配器

单元测试不能依赖中国政府采购网实时可访问，否则网络波动会让测试不稳定。

`tests/test_runner.py` 里定义了 `FakeAdapter`：

```python
class FakeAdapter:
    def collect(self, bidql, *, max_pages=1, max_results=10):
        return [Notice(...)]
```

测试目标不是证明公开网站在线，而是证明服务层拿到 Notice 后会正确生成 Word、outbox、trace、checkpoint 和 runlog。

真实网站验证仍然保留在人工/烟测命令里。

## API 如何触发运行

`POST /api/runs` 做四件事：

1. 读取 `query`。
2. 解析 `now`、`max_pages`、`max_results`。
3. 校验数字必须为正整数。
4. 调用 `run_once()` 并返回 `RunOnceResult.to_dict()`。

核心代码：

```python
return run_once(
    settings=settings,
    query=query,
    now=now,
    max_pages=max_pages,
    max_results=max_results,
).to_dict()
```

API 不知道采集细节，也不直接写 Word。它只是 HTTP 壳，业务逻辑都在服务层。

## 前端状态流

`web/dist/app.js` 维护一个很小的状态：

```javascript
const state = {
  currentRunId: null,
  running: false,
};
```

点击运行时：

1. 禁用按钮。
2. `POST /api/runs`。
3. 用返回值更新运行摘要。
4. 刷新 outbox。
5. 拉取 `/api/traces/{run_id}`。
6. 拉取 `/api/checkpoints/{run_id}`。
7. 恢复按钮。

这条链路保证 UI 展示的是后端真实运行结果。

## 响应式布局

桌面端使用三栏：

```text
query | run/checkpoint | trace
outbox spans full width
```

移动端改为单栏：

```text
query
run
trace
checkpoint
outbox
```

P4 验证中发现移动端横向溢出，原因是网格子项和表单控件缺少 `min-width: 0`。修复后 390px 视口的 `scrollWidth` 等于 `innerWidth`。

## 为什么不用 React

当前阶段 UI 只有一个工作台页面，交互集中在少量 API 调用和 DOM 更新上。引入 React/Vite 会增加依赖、构建脚本和部署步骤，但不会让 P4 的目标更真实。

因此本阶段采用静态 HTML/CSS/JS。后续如果进入复杂订阅管理、筛选、批量任务和登录站账号态管理，再迁移到 React 更合适。

## 验证方法

运行：

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
```

浏览器验证：

```text
http://127.0.0.1:8001/
```

Playwright 已验证：

- 首屏不是空白。
- 没有框架错误覆盖层。
- 点击 `运行采集` 后状态完成。
- trace 事件数为 10。
- checkpoint 数为 3。
- outbox 下载入口可见。
- 移动端无横向溢出。

## 下一阶段如何接上

P5 适合做定时任务和订阅：

- 把含频率的意图写入 `subscriptions`。
- APScheduler 根据 cron 触发 `run_once()`。
- 使用 `sent_history` 过滤已推送 cluster。
- UI 增加订阅列表和定时任务状态。
