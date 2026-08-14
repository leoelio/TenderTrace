# TenderTrace 飞书记录视图

该插件对应飞书应用 `cli_aafe28a6bef85be2` 的记录视图能力
`blk_6a7494bb1fc08bedb9cfd52b`。它读取当前多维表格记录，并调用 TenderTrace
机会情报 API，展示机会等级、质量分项、项目目标、策略、风险和角色行动。

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
