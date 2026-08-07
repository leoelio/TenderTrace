# P16 Demo 视频生成与交付闭环

## 阶段目标

P16 把 Demo 视频从待人工录制推进到可交付文件。新增 `demo-video` 命令，从当前真实 Web UI 截图和 `demo-check` 证据包生成 MP4：

```powershell
python -m tendertrace demo-video --url http://127.0.0.1:8015/ --out docs/demo/demo演示视频.mp4
```

当前生成文件：

```text
docs/demo/demo演示视频.mp4
```

视频参数经 `ffprobe` 验证：

```text
width=1280
height=720
duration=20.000000
nb_frames=600
```

## 生成逻辑

`demo-video` 做四件事：

1. 读取当前 `demo-check` 证据。
2. 用 Playwright 截取运行中的 Web 工作台画面。
3. 用 Pillow 生成带标题、证据摘要和 UI 截图的帧。
4. 用 ffmpeg 编码为 MP4，并重新写出 `docs/demo/demo_evidence_latest.json`。

它不硬编码公告结果；视频里的 run 数、query 数、outbox 数、trace 工具和 warning 来自当前数据库和文件系统。

## Browser 回退说明

本阶段按前端验证流程优先尝试内置 Browser。当前环境返回：

```text
Browser is not available: iab
agent.browsers.list() = []
```

因此回退到普通 Playwright。回退后已验证：

- 页面标题为 `TenderTrace 工作台`。
- 页面非空。
- 控制台无 error/warn。
- Playwright 截图非空。

## 当前验收状态

生成视频后：

```powershell
python -m tendertrace demo-check --out docs/demo/demo_evidence_latest.json
```

结果：

```text
status=pass
pass=6
warn=1
fail=0
```

唯一 warning：

```text
qianlima login_required
```

## 成功标准

1. `docs/demo/demo演示视频.mp4` 存在且大于 10 KB。
2. 视频为 1280x720，时长约 20 秒。
3. 首帧不是黑屏，中文标题和 Web 截图可读。
4. `demo-check` 的 `demo_video_file` 通过。
5. `acceptance-check` 检查 Demo 视频文件。

## 验证命令

```powershell
python -m tendertrace demo-video --url http://127.0.0.1:8015/ --out docs/demo/demo演示视频.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,duration,nb_frames -of json docs/demo/demo演示视频.mp4
python -m tendertrace demo-check --out docs/demo/demo_evidence_latest.json
python -m tendertrace acceptance-check
python -m unittest discover -s tests -v
python -m ruff check .
```

## 当前剩余项

千里马仍需人工免费会员登录：

```powershell
python -m tendertrace login-qianlima
python -m tendertrace verify-qianlima
```

该项是外部账号登录状态，不应在代码或文档中保存账号密码。
