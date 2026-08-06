# 05 定时订阅与 sent_history 增量

## 本阶段解决什么问题

P5 解决的是赛题中的“如果用户意图中涉及发送的时间和频率，需定时触发”和“定时推送只包含新增内容”。这不是简单地加一个定时器，而是要把一次性运行变成可重复、可审计、可去重的订阅运行。

本阶段的核心设计是：

- 自然语言问题仍先编译为 BidQL。
- 如果 BidQL 中存在 `schedule`，就允许创建订阅。
- 订阅保存原始问题，而不是只保存一次性解析结果。
- 每次触发订阅时重新执行 `run_once()`。
- `sent_history` 记录每个订阅已经推送过的公告 cluster，下一次过滤掉重复公告。
- 每次运行仍写入 Word、outbox、trace、checkpoint 和 runlog。

## 源码地图

- `tendertrace/scheduling/subscriptions.py`：订阅的创建、列表、运行。
- `tendertrace/scheduling/scheduler.py`：把订阅转换成 APScheduler job。
- `tendertrace/scheduling/ledger.py`：增量发送账本。
- `tendertrace/runner.py`：在运行图中加入增量过滤和发送历史写入。
- `tendertrace/app/api.py`：Web API 和服务生命周期。
- `web/dist/app.js`：浏览器端创建订阅、刷新订阅、手动触发订阅。
- `tests/test_subscriptions.py`：用稳定假适配器证明第二次不重复推送。
- `tests/test_scheduler.py`：证明 cron 订阅会注册成调度任务。

## 为什么订阅要保存 original_query

`create_subscription()` 的核心代码：

```python
bidql = compile_intent(query, now=now)
schedule = bidql.get("schedule", {})
schedule_kind = str(schedule.get("kind") or "immediate")
if schedule_kind == "immediate":
    raise ValueError("subscription query must include a sending time or frequency")
bidql["_runtime"] = {"max_pages": max_pages, "max_results": max_results}
```

这里有两个关键点：

1. 只有带发送时间或频率的问题才能成为订阅。
2. 订阅保存 `original_query`，同时保存一份创建时的 BidQL 快照。

为什么不只保存 BidQL？因为“最近3个月”这种时间表达是滚动窗口。假设今天是 2026-07-06，最近3个月是一个范围；明天运行时，最近3个月的窗口应该随日期前移。如果只保存一次解析后的绝对时间范围，订阅就会失去“持续关注”的意义。

因此 `run_subscription()` 每次触发时仍把原始问题交给 `run_once()`：

```python
result = run_once(
    settings=settings,
    query=subscription.original_query,
    now=now,
    max_pages=max_pages,
    max_results=max_results,
    adapter=adapter,
    subscription_id=subscription.id,
    incremental=True,
)
```

`subscription_id` 告诉运行器这是哪个订阅，`incremental=True` 告诉运行器需要启用增量过滤。

## 调度器如何工作

`scheduler.py` 做的是把数据库中的 active 订阅注册到 APScheduler：

```python
scheduler = BackgroundScheduler(timezone=settings.timezone)
for subscription in list_subscriptions(settings):
    schedule_subscription(scheduler, settings, subscription)
scheduler.start()
```

这段代码通常在 FastAPI lifespan 启动时执行。服务启动后，系统会扫描当前所有有效订阅，并为它们注册后台任务。

单个订阅注册 job 的代码：

```python
scheduler.add_job(
    run_subscription,
    trigger=trigger,
    id=f"subscription:{subscription.id}",
    kwargs={"settings": settings, "subscription_id": subscription.id},
    replace_existing=True,
    coalesce=True,
    max_instances=1,
)
```

这些参数有实际意义：

- `id=f"subscription:{subscription.id}"`：每个订阅有稳定 job id。
- `replace_existing=True`：服务重启或重复注册时不会产生多个相同任务。
- `coalesce=True`：如果错过多次触发，合并为一次执行。
- `max_instances=1`：同一个订阅不会并发跑两次，避免重复写报告和 `sent_history`。

cron 订阅来自 BidQL 的 `cron` 字段：

```python
if subscription.schedule_kind == "recurring" and subscription.cron:
    minute, hour, day, month, day_of_week = subscription.cron.split()
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone=subscription.timezone,
    )
```

例如“每天9:00发送给我”会被解析成 `0 9 * * *`。

## sent_history 如何避免重复

`sent_history` 的职责很窄：记录某个订阅已经发送过哪些公告 cluster。

写入函数：

```python
def mark_sent(conn, *, subscription_id, cluster_key, run_id, docx_path) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO sent_history(subscription_id, cluster_key, run_id, docx_path)
        VALUES (?, ?, ?, ?)
        """,
        (subscription_id, cluster_key, run_id, docx_path),
    )
    return cursor.rowcount == 1
```

这里用 `INSERT OR IGNORE`，前提是数据库里对 `(subscription_id, cluster_key)` 做唯一约束。这样同一个订阅同一条公告只能写入一次。

查询未发送 cluster：

```python
keys = list(dict.fromkeys(cluster_keys))
rows = conn.execute(
    f"""
    SELECT cluster_key FROM sent_history
    WHERE subscription_id = ? AND cluster_key IN ({placeholders})
    """,
    (subscription_id, *keys),
).fetchall()
sent = {row["cluster_key"] for row in rows}
return [key for key in keys if key not in sent]
```

这里先用 `dict.fromkeys()` 去掉输入列表里的重复 key，并保持原顺序。返回值仍按采集结果顺序排列，便于报告顺序稳定。

## runner 中的增量过滤

P5 没有另写一条订阅专用流水线，而是在原来的 `run_once()` 中增加两个参数：

```python
subscription_id: str | None = None,
incremental: bool = False,
```

采集节点先拿到源站结果：

```python
notices = source_adapter.collect(
    state.intent,
    max_pages=max_pages,
    max_results=max_results,
)
collected_count = len(notices)
```

如果是订阅增量模式，再查询 `sent_history`：

```python
if subscription_id and incremental:
    cluster_keys = [_cluster_key(notice.to_dict()) for notice in notices]
    with connection(settings) as conn:
        unsent = set(
            unsent_cluster_keys(
                conn,
                subscription_id=subscription_id,
                cluster_keys=cluster_keys,
            )
        )
    notices = [
        notice
        for notice in notices
        if _cluster_key(notice.to_dict()) in unsent
    ]
```

这段代码的作用是：源站仍然可以返回完整列表，但进入报告的只剩未推送过的公告。

随后写入 funnel 统计：

```python
funnel={
    "collected": collected_count,
    "new": len(notices),
    "skipped_sent": collected_count - len(notices),
}
```

这让 UI、runlog 和测试都能清楚看到：采集到多少、真正新增多少、因为已发送跳过多少。

## cluster_key 是什么

去重不能只靠标题，因为不同站点可能改标题，也可能同标题不同项目。因此系统使用 `_cluster_key()`：

```python
def _cluster_key(notice: dict[str, object]) -> str:
    fields = notice.get("fields")
    if isinstance(fields, dict) and fields.get("cluster_key"):
        return str(fields["cluster_key"])
    source_site = str(notice.get("source_site") or "")
    notice_id = str(notice.get("id") or "")
    if source_site and notice_id:
        return f"{source_site}:{notice_id}"
    return str(notice.get("source_url") or notice_id)
```

优先级是：

1. 适配器提供的规范化 `fields.cluster_key`。
2. `source_site:id`。
3. `source_url`。

这给后续多源站去重留下了扩展口。当前 P5 的重点是同一订阅内不重复推送，后续可以在清洗聚合阶段把跨站相似公告归并成统一 cluster。

## 为什么没有新增内容也生成 Word

赛题要求定时推送只包含新增内容。这里有两种实现：

1. 没有新增内容就完全不生成文件。
2. 没有新增内容也生成一份“本次无新增”的 Word。

P5 选择第二种。原因是定时任务必须可追踪、可验证。生成空结果报告后，用户能在 outbox 中看到任务确实执行过，也能通过 trace 和 checkpoint 追溯本次运行。

报告模式会标记为：

```python
run_mode="incremental" if incremental else "full"
```

这样 Word 内部和 runlog 都能区分立即全量运行与订阅增量运行。

## API 如何把调度器接入服务生命周期

FastAPI 使用 lifespan 管理后台调度器：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scheduler = None
    if settings.scheduler_enabled:
        app.state.scheduler = start_subscription_scheduler(settings)
    try:
        yield
    finally:
        scheduler = app.state.scheduler
        if scheduler is not None:
            scheduler.shutdown(wait=False)
```

服务启动时注册调度器，服务关闭时停止调度器。这样不会留下后台线程。

创建订阅 API 成功后，如果当前服务已经启动调度器，会立即把新订阅加入调度器：

```python
if app.state.scheduler is not None:
    schedule_subscription(app.state.scheduler, settings, subscription)
```

这意味着用户在 Web UI 中创建订阅后，不需要重启服务也会生效。

## 前端如何触发订阅

`app.js` 新增了三个函数：

```javascript
async function refreshSubscriptions() {
  const payload = await api("/api/subscriptions");
  renderSubscriptions(payload.items || []);
}
```

`refreshSubscriptions()` 负责刷新订阅表。

```javascript
async function createSubscriptionFromForm() {
  const query = el.queryInput.value.trim();
  const subscription = await api("/api/subscriptions", {
    method: "POST",
    body: JSON.stringify({
      query,
      max_pages: Number(el.maxPagesInput.value || 1),
      max_results: Number(el.maxResultsInput.value || 10),
    }),
  });
  await refreshSubscriptions();
}
```

`createSubscriptionFromForm()` 复用现有输入框。区别是它调用 `/api/subscriptions`，而不是 `/api/runs`。

```javascript
async function triggerSubscription(subscriptionId) {
  const result = await api(`/api/subscriptions/${encodeURIComponent(subscriptionId)}/run`, {
    method: "POST",
  });
  renderRunSummary(result);
  await Promise.all([refreshSubscriptions(), refreshOutbox(), refreshTrace(result.run_id)]);
}
```

`triggerSubscription()` 是演示和验证阶段最重要的入口。它让我们不用等到真实 9 点，也能证明订阅链路和增量链路正确。

## 测试如何证明增量正确

`tests/test_subscriptions.py` 使用 `StableAdapter`，每次都返回同一条公告：

```python
class StableAdapter:
    def collect(self, bidql, *, max_pages: int = 1, max_results: int = 10) -> list[Notice]:
        return [
            Notice(
                id="stable-notice-1",
                source_site="ccgp",
                title="上海某单位服务器采购公开招标公告",
                ...
            )
        ]
```

测试连续运行同一个订阅两次：

```python
first = run_subscription(...)
second = run_subscription(...)
```

断言重点：

```python
self.assertEqual(first.notice_count, 1)
self.assertEqual(second.notice_count, 0)
self.assertEqual(first_run["stats"]["new"], 1)
self.assertEqual(second_run["stats"]["skipped_sent"], 1)
self.assertEqual(len(sent_rows), 1)
self.assertEqual(sent_rows[0]["cluster_key"], "ccgp:stable-notice-1")
```

这组断言比只看 Word 是否生成更强，因为它证明了：

- 第一次确实把公告作为新增内容输出。
- 第二次确实因为 `sent_history` 跳过同一公告。
- `sent_history` 没有重复写入。
- runlog 里能看到增量统计。

## 本阶段验收命令

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
```

当前结果：

- 34 个测试通过。
- Ruff 通过。
- API 烟测中同一订阅第一次运行 `notice_count = 2`，第二次运行 `notice_count = 0`。
- Web 烟测中订阅创建、手动触发、trace 查看、outbox 下载均可用。

## 你需要掌握的关键概念

1. 订阅不是定时器本身，而是“原始问题 + 计划 + 运行参数 + 状态”的持久化实体。
2. 调度器只负责按时间调用 `run_subscription()`，不负责采集、清洗、写 Word。
3. 增量去重必须写数据库账本，不能只靠内存，否则服务重启后会重复推送。
4. `sent_history` 必须按 `subscription_id` 隔离，不同订阅之间不应该互相影响。
5. 同一条 `run_once()` 链路被 CLI、API、UI、调度器复用，系统行为才容易保持一致。
