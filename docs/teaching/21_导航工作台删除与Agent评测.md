# 21 导航工作台删除与 Agent 评测

## 学习目标

这一节讲解三个工程点：

1. 如何把一个单页工具 UI 拆成多视图工作台，但仍然复用同一套 API。
2. 如何设计删除操作，使“删除文件”和“删除记录”语义清楚。
3. 如何为 RAG + Agent 系统建立第一版可运行评测面板。

## 一、为什么先改导航，不先加复杂状态管理

本项目当前前端是原生 HTML、CSS、JavaScript。这里没有引入 React/Vue，也没有引入路由库。原因很简单：当前需求是产品化工作台，不是复杂前端工程。

导航的实现核心是 `data-view`：

```html
<button class="nav-tab active" type="button" data-view="workbenchView">工作台</button>
<button class="nav-tab" type="button" data-view="evaluationView">Agent评测</button>
```

JS 只需要读取这个属性：

```javascript
function showView(viewId) {
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === viewId);
  });
}
```

这段代码的价值在于：页面视图切换由 DOM 属性表达，不需要维护额外路由对象。对于比赛交付，这比上前端框架更稳。

## 二、删除功能为什么拆成三个接口

删除有三种不同语义：

- 删除 Word 文件：用户不想保留 outbox 文件。
- 删除运行记录：用户不想在历史里看到某次 run。
- 删除订阅任务：用户不想继续定时执行。

如果只做一个泛化删除接口，用户很难理解后果。因此后端拆成：

```text
DELETE /api/outbox/{filename}
DELETE /api/runs/{run_id}
DELETE /api/subscriptions/{subscription_id}
```

运行记录删除采用软删除，不直接删除 `runs` 行。原因是 `sent_history` 需要保留 `run_id`，否则订阅增量去重会被破坏：

```python
conn.execute("DELETE FROM outbox_messages WHERE run_id = ?", (run_id,))
conn.execute("DELETE FROM trace_events WHERE run_id = ?", (run_id,))
conn.execute("DELETE FROM run_checkpoints WHERE run_id = ?", (run_id,))
conn.execute("UPDATE runs SET status = 'deleted' WHERE id = ?", (run_id,))
```

这是有意设计。运行记录是展示历史，Word 文件是交付产物，`sent_history` 是增量账本。三者的生命周期不完全相同。

## 三、前端为什么用事件委托处理删除

outbox、历史运行、订阅表格都是动态渲染的。表格行每次刷新都会重建，因此不适合给每个按钮单独绑定事件。

前端采用事件委托：

```javascript
document.addEventListener("click", (event) => {
  const deleteRunTarget = event.target.closest("[data-delete-run-id]");
  if (deleteRunTarget) {
    deleteRun(deleteRunTarget.dataset.deleteRunId);
  }
});
```

这样做的好处是：

- 表格重新渲染后按钮仍然有效。
- 事件绑定只有一处。
- 删除 outbox、run、subscription 可以统一入口分发。

每个删除函数都会先弹出确认：

```javascript
if (!window.confirm("确认删除这条运行记录？Word 文件不会随记录一起删除。")) return;
```

确认文案必须说清楚后果，尤其是“是否删除 Word 文件”。

## 四、Agent 评测为什么放进后端

评测不应该由前端自己算。前端只负责展示，指标定义应该在后端统一生成。

后端新增：

```python
@app.get("/api/evaluations/agent")
def agent_evaluation() -> dict[str, object]:
    return build_agent_evaluation_report(settings)
```

`build_agent_evaluation_report()` 汇总四类指标：

- RAG：证据通过率、附件抽取率、报告产出率。
- Agent：checkpoint 完成率、平均事件数、失败率。
- Harness：固定自然语言样例的字段准确率。
- Recall：来源覆盖、去重保留、多源命中的代理召回指标。

## 五、召回率为什么暂时叫 recall_proxy

严格召回率需要知道“真实应该召回的全集”。招投标互联网场景中，这个全集通常不存在，除非人工构造标注集。

所以当前实现返回：

```python
"strict_recall_available": False
```

并计算可运行代理指标：

```python
recall_proxy = 0.45 * source_coverage + 0.35 * dedup_retention + 0.20 * multi_source_rate
```

这不是偷换概念，而是把工程现实讲清楚：当前系统可以评估覆盖倾向，但不能声称严格召回率。

## 六、如何验证这一阶段

运行：

```powershell
node --check web\dist\app.js
python -m unittest discover -s tests -v
python -m ruff check tendertrace tests
```

再启动 Web：

```powershell
$env:TENDERTRACE_PORT='8011'
python -m tendertrace serve
```

打开：

```text
http://127.0.0.1:8011/
```

检查：

- 顶栏是否包含 `Agent评测`。
- 工作台是否保持左右布局。
- 历史运行是否有删除记录按钮。
- 订阅管理是否有删除按钮。
- Agent评测是否展示 RAG、Agent、Harness、召回覆盖。

## 七、扩展思考

后续如果要做严格评测，可以加一个 `golden_corpus` 表：

- `query`
- `expected_notice_ids`
- `expected_sources`
- `expected_time_window`
- `labeler`

然后在 `evaluation.py` 中增加真实 recall、precision、F1。当前阶段先做可运行评测，是为了让系统有持续改进的仪表盘。
