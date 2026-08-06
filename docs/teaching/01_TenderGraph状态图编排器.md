# 01 TenderGraph 状态图编排器

## 本阶段解决什么问题

P1 把 TenderTrace 的“流程”做成一等公民。后续意图解析、源规划、采集、清洗、去重、校验、报告都会是图上的节点，而不是散落在一个大函数里的顺序调用。

这样做有三个直接收益：

- 条件路由清楚：`verify` 可以根据质量结果决定去 `repair` 还是 `report`。
- 失败可恢复：每个成功节点后保存 `RunState`，失败后从最近检查点继续。
- 过程可追踪：节点开始、工具调用、节点结束都会写进 `trace_events`。

## 源码地图

- `tendertrace/runtime/state.py`：定义 `RunState`，即一次任务的状态快照。
- `tendertrace/runtime/bus.py`：定义 `RuntimeEvent`、`EventBus`、`RunContext`。
- `tendertrace/runtime/graph.py`：定义 `TenderGraph` 和图执行逻辑。
- `tendertrace/runtime/checkpoint.py`：把每个成功节点后的状态保存到 `run_checkpoints`。
- `tendertrace/runtime/trace.py`：把事件流保存到 `trace_events`。
- `tendertrace/cli.py`：新增 `graph-smoke`，跑一个最小演示图。
- `tendertrace/app/api.py`：新增 trace 和 checkpoint 查询接口，供后续 UI 使用。
- `tests/test_runtime_graph.py`：验证顺序执行、条件路由和失败恢复。

## RunState：为什么用状态快照

`RunState` 是一个 dataclass，字段覆盖后续流水线需要的核心数据：

- `intent`：意图解析结果。
- `source_plan`：数据源计划。
- `candidates` / `notices` / `clusters`：采集、清洗、去重后的数据。
- `quality`：校验结果。
- `funnel`：漏斗统计。
- `artifacts`：报告和输出文件。
- `errors`：失败信息。

节点不直接修改原对象，而是调用 `with_updates()` 返回新状态。这样每个检查点都是一个稳定快照，便于回放和调试。

## EventBus：事件为什么单独做

事件流和状态快照不是一回事。

状态快照回答“现在任务的数据是什么”；事件流回答“系统刚刚做了什么”。例如：

- `node_started`：某个 Agent 开始执行。
- `tool_called`：节点内部调用了某个工具。
- `node_finished`：节点执行完成。
- `node_failed`：节点失败。
- `run_finished`：整次运行结束。

P1 的 `EventBus` 很小，只做发布和订阅。`SqliteTraceStore` 订阅它之后，每个事件都会被持久化。后续 Web UI 的 SSE 时间线也会订阅同一条事件流。

## TenderGraph：执行循环

`TenderGraph` 内部维护三类结构：

- `_nodes`：节点名到函数的映射。
- `_edges`：普通边，表示固定下一步。
- `_routers`：条件边，表示下一步由状态决定。

执行流程：

1. 找到入口节点。
2. 发布 `node_started`。
3. 调用节点函数，节点接收 `RunState` 和 `RunContext`。
4. 节点可以通过 `context.emit_tool_call()` 记录工具调用。
5. 节点成功后保存检查点。
6. 发布 `node_finished`。
7. 根据普通边或条件边进入下一节点。
8. 没有下一节点时发布 `run_finished`。

## 检查点恢复

`SqliteCheckpointer.latest(run_id)` 会取最近的成功节点。`TenderGraph.run(..., resume=True)` 会加载这个状态，并从该节点的下一节点继续执行。

这意味着：如果 `first` 成功、`second` 失败，第二次运行不会重复执行 `first`，而是直接从 `second` 继续。

## 为什么 P1 不做更复杂的能力

本阶段没有做并发节点、子图、异步执行和分布式队列。原因是当前项目是单机交付，第一目标是可演示和可回放。复杂能力只有在真实采集阶段出现性能瓶颈后才值得加入。

## 验证方法

运行：

```powershell
python -m unittest discover -s tests -v
python -m tendertrace graph-smoke
```

重点看三类测试：

- 正常图会生成完整事件序列。
- 条件图会走一次 `verify -> repair -> collect` 回路。
- 失败图能从检查点恢复。

## 下一阶段如何接上

P2 会把 `intent` 节点替换成真实的 BidQL 意图编译器。届时 `RunState.intent` 会开始保存主题、地区、时间 AST 和调度计划，`graph-smoke` 中的假数据会被真实解析结果替代。
