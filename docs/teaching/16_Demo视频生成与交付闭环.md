# 16 Demo 视频生成与交付闭环

这一节解释 `demo-video` 为什么这样设计，以及它如何把 Demo 视频变成可重复生成的交付物。

## 为什么不只放一个手工视频

手工录屏当然可以交付，但它有两个问题：

- 很难验证视频对应当前代码和当前数据。
- 录屏失败后需要重新操作一整套流程。

`demo-video` 采用“当前证据 + 当前 UI 截图 + 自动编码”的方式。它不是伪造结果，而是把项目已经产生的 run、trace、outbox、订阅和 warning 组织成一个可看的 MP4。

## 输入来源

视频内容来自三类真实证据：

1. `demo-check`：读取 SQLite、outputs、outbox、sent_history、模型状态、来源状态。
2. Playwright 截图：访问运行中的 Web UI。
3. ffmpeg：把帧序列编码成 MP4。

因此视频不是静态模板。当前数据库里的 run 数、query 数、trace 工具和 warning 会影响视频内容。

## 核心函数

`tendertrace/demo_video.py` 提供：

```python
generate_demo_video(settings, url, output_path, evidence_path)
capture_web_screenshots(url, output_dir)
render_demo_frames(report, screenshot_paths, output_dir)
```

其中 `generate_demo_video()` 是总入口：

1. 抓 Web 截图。
2. 运行 `run_demo_check()`。
3. 渲染帧。
4. 调用 ffmpeg。
5. 再运行一次 `run_demo_check()` 刷新证据包。

最后一步很关键，因为视频生成后，`demo_video_file` 应该从 warning 变成 pass。

## 为什么先尝试 Browser 再回退 Playwright

前端验证优先使用内置 Browser。但当前环境没有可用 Browser：

```text
agent.browsers.list() = []
```

所以 P16 回退到普通 Playwright。回退不是偷懒，而是因为内置 Browser 实际不可用；这点已写入 P16 操作文档。

## ffmpeg 参数问题

第一次生成时发现视频只有 0.67 秒。原因是命令里错误地使用了 `-frames:v 20`，导致输出端只保留 20 帧。

修正后使用输入帧率控制时长：

```text
-framerate 1 -i frame_%04d.png -c:v libx264 -pix_fmt yuv420p -r 30
```

最终结果：

```text
duration=20.000000
nb_frames=600
```

这个问题说明：视频交付不能只看文件存在，还要检查时长和分辨率。

## 测试覆盖

`tests/test_demo_video.py` 不跑浏览器和 ffmpeg，因为这些属于环境集成能力。它测试：

- 帧生成是否使用 report evidence 和截图。
- 输出结果对象是否 JSON 安全。

集成验证由实际命令完成：

```powershell
python -m tendertrace demo-video --url http://127.0.0.1:8015/ --out docs/demo/TenderTrace_Demo.mp4
ffprobe ...
```

## 当前交付状态

当前已经生成：

```text
docs/demo/TenderTrace_Demo.mp4
docs/demo/demo_evidence_latest.json
```

`demo-check` 当前结果：

```text
pass=6
warn=1
fail=0
```

唯一 warning 是千里马登录态缺失，仍需人工完成免费会员登录。
