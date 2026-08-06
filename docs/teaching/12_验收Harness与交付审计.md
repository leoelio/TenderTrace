# 12 验收 Harness 与交付审计

## 本阶段解决什么问题

项目越接近交付，越不能只靠“我记得已经做了”。P12 的目标是把交付要求变成一个可运行的验收命令：

```powershell
python -m tendertrace acceptance-check
```

这个命令会检查设计文档、操作文档、Demo 脚本、Word 输出、outbox、数据库表、模型状态、来源状态、敏感信息扫描和运行证据。

## 源码地图

- `tendertrace/acceptance.py`：验收检查逻辑。
- `tendertrace/cli.py`：命令行入口。
- `tests/test_acceptance.py`：验收逻辑测试。
- `docs/operation/P12_验收Harness与交付审计.md`：操作记录。
- `docs/teaching/12_验收Harness与交付审计.md`：本教学文档。

## AcceptanceCheck

每个检查项都是一个简单数据对象：

```python
@dataclass(frozen=True)
class AcceptanceCheck:
    name: str
    status: str
    detail: str
```

`status` 只有三类：

- `pass`：满足要求。
- `warn`：功能存在，但需要人工关注。
- `fail`：交付阻塞。

为什么要有 `warn`？

例如千里马登录态。代码已经实现登录源，但本机可能还没执行免费会员登录。这个状态应该提醒用户，而不应该把整个代码交付判定为失败。

## AcceptanceReport

报告对象会汇总所有检查：

```python
@dataclass(frozen=True)
class AcceptanceReport:
    status: str
    checks: list[AcceptanceCheck]
```

只要有一个 `fail`，总状态就是 `fail`。`warn` 不会让命令失败。

## 为什么不读取 .env.local

`.env.local` 里可能有真实 OpenAI key。验收命令只调用：

```python
model_status(settings).to_dict()
```

这个接口只返回：

- mode
- provider
- model
- configured
- enhancement_enabled

不会返回 key 内容。

## 敏感信息扫描

扫描范围：

- README
- `.env.example`
- docs
- tendertrace
- tests
- web
- pyproject.toml

不扫描：

- `.env.local`
- data
- outputs
- outbox
- snapshots
- secrets

正则：

```python
SECRET_PATTERN = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}|Bearer\\s+sk-[A-Za-z0-9_-]+")
```

这样可以发现误写进模板或文档的 OpenAI key。

## 为什么检查 .env.example

模板文件应该只写变量名，不写真实值：

```env
OPENAI_API_KEY=
```

P12 专门检查这一点，避免把本地 key 带进交付包。

## 数据库检查

验收命令使用 `database_health(settings)` 检查：

- 数据库是否初始化。
- 核心表是否存在。
- `schema_migrations` 是否包含 v5。

核心表包括：

- `runs`
- `trace_events`
- `run_checkpoints`
- `subscriptions`
- `sent_history`
- `notices`
- `clusters`
- `evidence_items`
- `attachment_snapshots`
- `model_audits`
- `outbox_messages`

这证明系统不是只有文件输出，还有可追踪账本。

## Word 产物检查

验收命令检查：

- `outputs/` 是否有 `.docx`。
- `outbox/` 是否有 `.docx`。
- 最新 Word 是否能被 `python-docx` 打开。
- 最新 Word 是否包含关键字段：
  - 标题
  - 发布时间
  - 来源链接
  - 核心内容

这不是视觉渲染检查，但能证明文件不是空壳。

## 运行证据检查

验收命令查询 `runs`：

- 是否有完成的 run。
- 最新 run 是否有 `notice_count`。
- 最新 run 是否有 `trace_events`。
- 最新 run 是否有 `evidence_checked`。
- 是否存在至少一个多来源 run。

这样可以证明系统曾经真实执行过采集、证据校验和多源聚合。

## CLI 如何接入

`cli.py` 新增：

```python
def cmd_acceptance_check(args: argparse.Namespace) -> int:
    settings = _settings()
    report = run_acceptance(settings, strict_runtime=not args.no_runtime)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.status == "pass" else 1
```

命令返回码很重要：

- 0：没有 fail。
- 1：至少一个 fail。

这样可以接入 CI 或交付前脚本。

## --no-runtime 的意义

干净环境刚 clone 项目时，可能还没有：

- outputs
- outbox
- runs

这时可以运行：

```powershell
python -m tendertrace acceptance-check --no-runtime
```

它不会严格要求运行产物，适合做安装后的预检。最终交付前应使用默认严格模式。

## 测试如何覆盖

`tests/test_acceptance.py` 使用临时目录创建最小交付结构：

- 文档文件。
- `.env.example`。
- 伪造 Word 报告。
- 初始化 SQLite。
- 插入完成 run 和模型审计。

然后断言 `run_acceptance()` 返回 `pass`。另一个测试会故意写入 `OPENAI_API_KEY=sk-proj-...`，确认扫描能失败。

## 本阶段你需要掌握的关键概念

1. 验收命令是交付质量的自动化入口。
2. `warn` 和 `fail` 应该区分，避免把可人工补齐项变成阻塞。
3. 敏感信息扫描必须排除真实 secret 文件，同时覆盖模板和文档。
4. Word 结构检查和视觉渲染检查不是一回事。
5. 最终交付前应同时跑 `acceptance-check`、单元测试和 Ruff。
