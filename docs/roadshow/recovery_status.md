# TenderTrace 恢复状态

更新日期：2026-09-04

- 保护分支：`codex/requirements-ledger-recovery-20260904`。
- 小目标 4 已提交为 `a3a5d22`：公告变化会精确映射到要求账本；页面以“待复核（原状态）”显示，数据库中的人工结论不被自动覆盖。
- 小目标 5 已实现但尚待本次 checkpoint：`GET /api/opportunities/{notice_id}/war-room` 返回无副作用的本地战情室编排计划，包含群卡片、主责任务、截止日历和多维表格四项前置条件。现有 `POST /api/opportunities/send-feishu` 是唯一会创建飞书资源的启动入口。
- 小目标 5 的本地计划不读取或输出任何密钥；真实飞书凭据仍只由环境变量或 `.env.local` 提供。
- 最近验证：飞书、机会、要求账本、公告变更和静态 Web 的 38 项测试通过；`ruff`、`node --check` 和 `git diff --check` 通过。
- 下一目标：小目标 6，会审工作流。开始前应保留本分支上未提交的 README、交付/验收/提交包和其他路演文档改动，除非它们被明确纳入任务。
