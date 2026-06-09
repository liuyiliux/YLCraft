# Tasks

## A: 在线配置平台模板
- [x] A1. 后端：`PUT /platform-templates/:id` + `DELETE /platform-templates/:id` API
- [x] A2. 前端：平台模板管理页（列表 + 编辑弹窗）

## B: 结果管理
- [x] B1. 后端：`POST /images/generate-batch/retry` — 单张重生成
- [x] B2. 前端：批量结果区加操作按钮（删除/替换重生成）

## C: 生成历史优化
- [x] C1. 后端：`generate-batch` 结果入库 AssetService
- [x] C2. 前端：历史卡片加 platform/topic + "跳到多平台生成"
- [x] C3. image-gen 页支持 URL 参数 `?tab=multi&topic=...&platforms=...`

## D: 批量主题并行 (P2)
- [x] D1. 多主题输入 + 任务队列编排
- [x] D2. 前端批量主题页

## E: 灵感获取 (P3)
- [x] E1. 复用 crawler，预留 xhs 平台接口
- [x] E2. 前端灵感页（由现有内容搜索页 `/crawler` 替代）
