# P19 UI 体验与检索召回优化

## 目标

本阶段解决 5 个问题：

1. Web UI 从表单面板改为对话式工作台，视觉更简洁。
2. 订阅、模型策略、搜索力度从隐含参数变成明确控件。
3. 修复“最近36个月杭州市空调/服务器投标信息”被误解析和召回不足的问题。
4. 解释翻页数和结果数，并用“搜索力度”映射默认参数。
5. 运行过程中显示进度消息、按钮 loading 和 pipeline 动画。

## 后端改动

### 城市解析

`tendertrace/intent/region.py` 新增城市别名表。当前覆盖杭州：

- `杭州市` -> `province=浙江`
- `city=杭州`
- `adcode=330000`
- `city_adcode=330100`

这样“杭州市”不再被误当成主题词。

### 主题解析

`tendertrace/intent/topic.py` 新增：

- `投标信息`、`全部投标信息` 等停用词。
- `空调` 领域扩展词：中央空调、空调设备、空调系统、暖通空调、制冷设备。
- `空调或者服务器` 多主题解析。
- `全部投标信息` 的开放主题标记 `open_scope=true`。

### GGZY 检索降级

`tendertrace/adapters/ggzy.py` 新增两层召回策略：

- 多关键词检索：核心词和扩展词会分别作为 `FINDTXT` 发送。
- 长时间窗降级：当时间范围超过站点可接受范围时，不发送超长 `TIMEBEGIN/TIMEEND`，改用站点默认相对时间参数，再由本地 BidQL 做事实过滤。

### 城市范围降级

`tendertrace/adapters/multi.py` 新增城市降级：

1. 先按城市精确匹配。
2. 如果该来源返回 0 条，再降级到省级范围。
3. `source_stats` 中记录 `relaxed_city=true`。

这不是硬编码结果，而是可解释的召回策略。

### 模型策略

`run_once` 和订阅运行新增 `model_strategy`：

- `config`：跟随 `.env.local`
- `rules`：只用本地规则
- `local`：Ollama 本地模型增强
- `cloud`：OpenAI 云端模型增强
- `hybrid`：本地规则 + 云端增强

CLI、API、Web UI 都可以传递该策略。

### 订阅计划覆盖

`create_subscription` 支持 UI 传入 `schedule` 对象：

- 每天
- 每周一
- 每月1日
- 今天一次

用户不再必须把“每天9:00”写进自然语言问题里。

## 前端改动

文件：

- `web/dist/index.html`
- `web/dist/app.js`
- `web/dist/styles.css`

主要变化：

- 主体改为对话式任务区。
- 输入框下方显示意图解析预览。
- 立即生成 / 订阅增量使用卡片式选择。
- 模型策略使用分段选择。
- 搜索力度使用快速、标准、深入三档。
- 翻页数和结果数放入高级采集范围。
- 运行时追加进度消息，并显示 loading 动画。
- 完成后在对话中返回命中条数和 Word 下载链接。

## 验证结果

针对用户指出的问题，真实运行结果：

```powershell
python -m tendertrace run-once "最近36个月杭州市的空调或者服务器投标信息都有哪些" --max-pages 5 --max-results 8 --model-strategy rules
```

结果：

```text
notice_count: 3
source_sites: ggzy
raw_count: 6
duplicates_removed: 3
relaxed_city: true
```

这说明系统先尝试杭州城市范围，若无结果再降级到浙江省范围，并仍保留空调/服务器主题过滤。

## 调试命令

```powershell
python -m tendertrace parse-intent "最近36个月杭州市的空调或者服务器投标信息都有哪些"
python -m tendertrace run-once "最近36个月杭州市的空调或者服务器投标信息都有哪些" --max-pages 5 --max-results 8 --model-strategy rules
python -m tendertrace source-status
python -m tendertrace acceptance-check
```

前端检查：

```powershell
node --check web\dist\app.js
python -m unittest tests.test_web_static tests.test_intent_compiler tests.test_ggzy_adapter tests.test_multi_source_adapter -v
```
