# P15 Demo 预检与录屏证据包

## 阶段目标

P15 面向最终 Demo 视频交付。视频本身仍需要人工录制，但录制前必须先证明当前工作区已经具备可演示证据：

- 多个自然语言问题的 finished run。
- Word 输出和 outbox 下载文件。
- 最新 run 的 trace 工具链。
- 订阅任务和 `sent_history` 增量记录。
- 模型状态和来源状态。
- 录屏文件是否已放入 `docs/demo/`。

因此本阶段新增 `demo-check` 命令，它只审计当前工作区，不联网、不重跑采集、不伪造演示结果。当前检查还会记录 CI 配置、最新交付包安全扫描和 API 鉴权状态。

## 新增命令

```powershell
python -m tendertrace demo-check
```

输出 JSON：

- `status`：只要没有核心缺失就是 `pass`。
- `counts`：pass/warn/fail 数量。
- `checks`：逐项检查结论。
- `evidence`：来自数据库、outputs、outbox、模型和来源状态的证据摘要。

写出证据包：

```powershell
python -m tendertrace demo-check --out docs/demo/demo_evidence_latest.json
```

## 当前工作区结果

当前预检结果：

```text
status=pass
pass=5
warn=2
fail=0
```

两个 warning 是透明保留的人工项：

- `sources`：千里马 `login_required`，需人工免费会员登录。
- `demo_video_file`：尚未在 `docs/demo/` 放入录屏文件。

## 成功标准

1. 没有 finished run 时，`demo-check` fail。
2. 只有一个问题或没有 Word/outbox 时，`demo-check` fail。
3. 最新 run 缺少关键 trace 工具时，`demo-check` fail。
4. 没有订阅或 `sent_history` 时，`demo-check` fail。
5. `.github/workflows/ci.yml` 缺失时 fail。
6. 已存在的提交包含禁入文件或疑似密钥时 fail；尚未生成提交包时只 warn，提醒最终交付前运行 `package-submission`。
5. 千里马未登录和视频未录制只作为 warning，不伪装成已完成。
6. 证据包不包含 OpenAI key、账号密码或 `.env.local` 明文。

## 验证命令

```powershell
python -m unittest tests.test_demo_check -v
python -m tendertrace demo-check
python -m tendertrace demo-check --out docs/demo/demo_evidence_latest.json
python -m unittest discover -s tests -v
python -m ruff check .
```

## 录屏前动作

1. 运行 `python -m tendertrace demo-check --out docs/demo/demo_evidence_latest.json`。
2. 确认没有 fail。
3. 如需要展示登录站，先运行 `python -m tendertrace login-qianlima`。
4. 按 `docs/demo/Demo演示脚本.md` 录制视频。
5. 将视频文件放入 `docs/demo/`，再运行一次 `demo-check`。
