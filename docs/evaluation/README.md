# TenderTrace 金标评测流程

本目录用于真实 Recall@K 评测。这里的金标不能由系统自动生成，否则会形成“系统召回什么就证明什么正确”的自证循环。

## 1. 生成候选标注包

```powershell
python -m tendertrace gold-candidates --max-pages 2 --max-results 30 --out docs/evaluation/gold_candidates_latest.json
```

该命令会读取 `gold_benchmark.json` 的 10 个查询，到配置的源站抓取候选公告，并输出标题、发布时间、来源链接和匹配键。

如果外部源站响应慢，可以逐 case 推进并断点续跑：

```powershell
python -m tendertrace gold-candidates --case-id gold-001 --case-timeout 45 --resume --out docs/evaluation/gold_candidates_latest.json
```

每个 case 都会输出 `finished`、`failed`、`timeout` 或 `cached` 状态，单个 case 失败不会阻断其他 case。

## 2. 人工标注

人工打开源站链接核验后，把确认“应召回”的公告填入对应 case 的 `gold_notices`：

```json
{
  "source_site": "ccgp",
  "notice_id": "站内公告 id，可选",
  "title": "公告标题",
  "publish_time": "2026-03-15 09:00",
  "source_url": "https://..."
}
```

至少填写 `source_url`。如果源站 URL 不稳定，可同时填写 `source_site + notice_id`。

## 3. 看标注覆盖率

```powershell
python -m tendertrace gold-coverage --out docs/evaluation/gold_coverage_latest.json
```

该命令不联网，用来确认哪些 case 已经具备人工 `gold_notices`，以及严格 Recall@K 是否已经可用。
## 4. 跑基准

```powershell
python -m tendertrace evaluate-gold --out docs/evaluation/recall_after_p22.json
```

当 `gold_notices` 为空时，命令会返回待标注状态，Agent 评测页继续显示 recall_proxy；一旦有人工金标，面板会显示真实 `Recall@5`、`Recall@10` 和 `Precision@10`。

当前仓库的 10 个 case 仍处于待人工标注状态。提交前若要展示严格 Recall@K，需要人工打开候选源站链接核验后填写 `gold_notices`；不能把系统召回结果直接写回金标。

## 5. 前后对比

每次检索策略变更前后各保存一份结果：

- `recall_baseline_before_change.json`
- `recall_after_change.json`

对比 `recall_at.10`，再决定是否保留改动。
