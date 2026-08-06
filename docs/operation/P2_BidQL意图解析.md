# P2 BidQL 意图解析

## 目标

P2 实现确定性规则通道，把自然语言查询编译成 BidQL。当前阶段不调用本地模型或 OpenAI 云端模型，模型增强通道留到后续安全配置后接入。

## 命令

```powershell
.\\.venv\\Scripts\\python -m tendertrace parse-intent "最近3个月的上海区域内的充电桩招标信息都有哪些，请汇总后每天9:00发送给我" --now "2026-07-06T10:00:00+08:00"
```

输出应包含：

- `topic.core`: `["充电桩"]`
- `region.province`: `上海`
- `time.kind`: `relative`
- `time.ast`: `{"op":"last","unit":"month","n":3}`
- `time.resolved_window`: `{"from":"2026-04-06","to":"2026-07-06"}`
- `schedule.kind`: `recurring`
- `schedule.cron`: `0 9 * * *`

## API

启动服务：

```powershell
.\\.venv\\Scripts\\python -m tendertrace serve
```

请求：

```http
POST http://127.0.0.1:8000/api/intent/parse
Content-Type: application/json

{
  "query": "2026年4月份上海的充电桩招标信息都有哪些，请汇总后今天9:00发送给我",
  "now": "2026-07-06T10:00:00+08:00"
}
```

关键输出：

- `time.kind = absolute`
- `time.from = 2026-04-01`
- `time.to = 2026-04-30`
- `schedule.kind = once_at`
- `schedule.time = 09:00`

## 验收命令

```powershell
.\\.venv\\Scripts\\python -m unittest discover -s tests -v
.\\.venv\\Scripts\\python -m ruff check .
.\\.venv\\Scripts\\python -m tendertrace graph-smoke
```

## 已知观察

测试中 `fastapi.testclient` 会输出一个 Starlette 依赖迁移告警，当前不影响接口行为。后续如果框架版本升级，再统一处理测试客户端依赖。
