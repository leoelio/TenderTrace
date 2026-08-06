# P12 验收 Harness 与交付审计

## 阶段目标

P12 把最终验收从人工清单变成可运行命令：

```powershell
python -m tendertrace acceptance-check
```

该命令不会读取或输出 `.env.local` 内容，只检查脱敏配置、交付文档、运行产物、数据库结构、模型状态、来源状态、Word 报告、trace 证据和敏感信息扫描结果。

## 成功标准

1. CLI 新增 `acceptance-check`。
2. 验收结果以 JSON 输出。
3. 有 `fail` 时命令返回非零退出码。
4. `warn` 不阻塞命令成功，但提示需要人工关注。
5. 默认严格检查运行产物；`--no-runtime` 可用于干净环境只查代码和文档结构。
6. 检查过程不输出 OpenAI key、不读取 `.env.local` 明文。

## 核心文件

- `tendertrace/acceptance.py`：验收检查实现。
- `tendertrace/cli.py`：新增 `acceptance-check` 命令。
- `tests/test_acceptance.py`：验收模块单元测试。
- `docs/operation/P12_验收Harness与交付审计.md`：本阶段操作记录。
- `docs/teaching/12_验收Harness与交付审计.md`：教学文档。

## 检查项

| 检查项 | 含义 |
|---|---|
| delivery docs | README、详设文档、操作文档、Demo 脚本、P12 文档存在 |
| teaching docx | 教学 Word 文件存在 |
| env example | `.env.example` 中 `OPENAI_API_KEY` 必须为空 |
| secret scan | 文档、代码、测试和模板不包含真实 OpenAI key 模式 |
| database | SQLite 初始化、核心表和 schema v5 存在 |
| model status | 模型通道已配置或给出 warning |
| sources | ccgp、ggzy 配置，qianlima 登录态缺失时 warning |
| outputs/outbox | 有 Word 运行产物 |
| latest report | 最新 Word 可被 `python-docx` 打开并包含关键字段 |
| run evidence | 至少有完成 run、trace、证据统计 |
| multi source | 至少一个完成 run 覆盖两个以上来源 |
| model audits | 有模型审计记录 |

## 命令

完整验收：

```powershell
python -m tendertrace acceptance-check
```

干净环境预检：

```powershell
python -m tendertrace acceptance-check --no-runtime
```

`--no-runtime` 不要求已有 outputs/outbox/run 记录，适合刚 clone 项目但还没跑采集时使用。

## 当前验收观察

当前环境中：

- Word/outbox 已存在。
- 数据库 schema 已到 v5。
- cloud/openai 模型通道已配置。
- 已有模型审计记录。
- 已有多源 run 证据。
- 千里马当前可作为登录态来源实现，但如果还没有保存 `storage_state`，验收命令会给出 `warn: login_required`。

## 注意事项

- `acceptance-check` 不替代全量测试。
- 最终交付前仍需运行：

```powershell
python -m unittest discover -s tests -v
python -m ruff check .
```

- Demo 录屏前建议先跑 `acceptance-check`，再按 `docs/demo/Demo演示脚本.md` 录制。
