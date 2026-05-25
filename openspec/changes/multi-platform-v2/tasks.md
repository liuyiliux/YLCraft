# Tasks

## A: 在线配置平台模板
- [ ] A1. 后端：`PUT /platform-templates/:id` + `DELETE /platform-templates/:id` API
- [ ] A2. 前端：平台模板管理页（列表 + 编辑弹窗）

## B: 结果管理
- [ ] B1. 后端：`POST /images/generate-batch/retry` — 单张重生成
- [ ] B2. 前端：批量结果区加操作按钮（删除/替换重生成）

## C: 生成历史优化
- [ ] C1. 后端：`generate-batch` 结果入库 AssetService
- [ ] C2. 前端：历史卡片加 platform/topic + "跳到多平台生成"
- [ ] C3. image-gen 页支持 URL 参数 `?tab=multi&topic=...&platforms=...`

## D: 批量主题并行 (P2)
- [ ] D1. 多主题输入 + 任务队列编排
- [ ] D2. 前端批量主题页

## E: 灵感获取 (P3)
- [ ] E1. 复用 crawler，预留 xhs 平台接口
- [ ] E2. 前端灵感页
