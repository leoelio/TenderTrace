# TenderTrace 飞书记录视图

该插件对应飞书应用 `cli_aafe28a6bef85be2` 的记录视图能力
`blk_6a7494bb1fc08bedb9cfd52b`。它读取当前多维表格记录，并调用 TenderTrace
机会情报 API，展示机会等级、质量分项、项目目标、策略、风险和角色行动。带有
`公告ID` 的记录还会读取本地机会库的负责人、销售阶段、资格门禁、投标决策和
Task v2 状态，并可执行当前阶段允许的工作流动作。

## 身份与动作边界

- 当前 Base 用户标识只作为动作审计主体，不会写入机会负责人的 `open_id`。
- 线索首次认领通过“发送认领卡”进入飞书会话，由成员点击卡片后获取真实
  `open_id`，再创建或复用分派给该成员的 Task v2。
- 认领后可以在记录视图执行机会确认、Go/Hold/No-Go、投标准备、结果标记和归档；
  所有动作复用 Web 端的阶段与资格门禁，失败时直接展示具体阻断原因。
- “决策依据”随 Go/Hold/No-Go 写入审计流并同步机会台账。

## 本地调试

```powershell
opdev login
cd integrations/feishu-record-view/opportunity-view
npm install
npm run start
```

首次进入插件后，在右上角设置中填写 TenderTrace API 地址。飞书页面通过 HTTPS
加载时，API 也应使用可访问的 HTTPS 地址，并加入应用的服务器域名白名单。
本地 `npm run start` 前还需要把实际多维表格 URL 写入 `opportunity-view/block.json`
的 `url` 字段；开发者后台的 `blk_...` 页面不能代替 Base 文档 URL。

## 构建与上传

```powershell
npm run build
npm run upload
```

上传需要先执行 `opdev login`，且登录用户必须拥有该应用和 BlockTypeID。
应用需要开通 `bitable:app` 或 `bitable:app:readonly` 用户身份权限并发布生效。
