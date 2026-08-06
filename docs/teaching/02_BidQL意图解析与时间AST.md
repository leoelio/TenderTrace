# 02 BidQL 意图解析与时间 AST

## 本阶段解决什么问题

P2 让系统能“听懂”用户问题。它不只是从句子里找几个词，而是把自然语言编译成 BidQL：主题、地区、时间表达式、调度计划、交付方式和置信度都放到一个结构化对象里。

本阶段只实现确定性规则通道。这样做是为了先把赛题的硬性槽位跑稳：地区、时间和调度都是封闭表达，规则比模型更可控，也更容易测试。

## 源码地图

- `tendertrace/intent/numbers.py`：中文数字转整数，如“三”“八”“十一”。
- `tendertrace/intent/time_expr.py`：解析“最近3个月”“2026年4月份”，并支持触发时刻求值。
- `tendertrace/intent/schedule.py`：解析“每天9:00”“今天9:00”“每周一早上八点半”。
- `tendertrace/intent/region.py`：省级行政区与别名识别。
- `tendertrace/intent/topic.py`：规则主题抽取、泛词清理、领域扩展词。
- `tendertrace/intent/compiler.py`：把各个槽位组装成 BidQL。
- `tests/test_intent_compiler.py`：赛题样例和对抗样例金标测试。
- `tests/test_api_intent.py`：验证 `/api/intent/parse` 接收 JSON body。

## 时间为什么存 AST

“最近3个月”不能在创建订阅时直接变成一个固定日期区间。因为订阅每天触发时，“最近3个月”的窗口应该跟着触发日期滚动。

所以 BidQL 里保存的是：

```json
{"kind":"relative","ast":{"op":"last","unit":"month","n":3}}
```

只有在某次运行真正触发时，才用 `resolve_window()` 和当前 `now` 求出具体区间。

绝对月份则不同：

```json
{"kind":"absolute","from":"2026-04-01","to":"2026-04-30"}
```

它永远固定，不随触发日期变化。

## 调度解析

`schedule.kind` 有三种：

- `immediate`：用户没有提发送时间或频率，立即执行。
- `once_at`：例如“今天9:00发送给我”，只触发一次。
- `recurring`：例如“每天9:00”“每周一早上八点半”，转成 cron。

示例：

```json
{"kind":"recurring","cron":"30 8 * * 1","time":"08:30","tz":"Asia/Shanghai"}
```

## 主题抽取

当前主题抽取是轻量规则：

1. 移除已识别的时间、地区和调度片段。
2. 移除“招标信息”“区域内”“请汇总后”等业务泛词。
3. 把“储能项目”归一为“储能”。
4. 用领域词典生成扩展词。

这不是最终智能形态。后续云端/本地模型通道会增强开放主题识别，但规则通道会一直保留，作为离线兜底和交叉校验来源。

## 为什么没有调用模型

用户要求本地模型和云端模型都要支持，但当前聊天里出现过明文 OpenAI Key。为了安全，P2 没有把这个 Key 写入文件，也没有发起云端调用。

本阶段先实现规则 BidQL。后续接入模型通道时，应只从 `.env.local` 或系统环境读取 `OPENAI_API_KEY`，并且日志只能显示 `openai_key_configured: true/false`。

## 验证方法

运行：

```powershell
python -m unittest discover -s tests -v
python -m tendertrace parse-intent "最近3个月的上海区域内的充电桩招标信息都有哪些，请汇总后每天9:00发送给我" --now "2026-07-06T10:00:00+08:00"
```

重点看：

- 赛题四条示例是否解析正确。
- 相对时间是否保存 AST。
- `resolve_window()` 是否在给定 `now` 下生成正确窗口。
- `每天9:00` 是否生成 `0 9 * * *`。
- `今天9:00` 是否生成 `once_at`。

## 下一阶段如何接上

P3 会开始第一个公开源采集闭环。BidQL 会被源规划 Agent 使用：地区决定站点和频道，时间窗口决定查询参数和翻页剪枝，主题和扩展词决定搜索关键词。
