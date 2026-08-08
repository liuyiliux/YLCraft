# Specs

## A. 在线配置平台模板
- `GET /api/v1/platform-templates/:id` — 单个模板详情
- `PUT /api/v1/platform-templates/:id` — 更新模板
- `DELETE /api/v1/platform-templates/:id` — 删除模板
- 前端页面 CRUD 管理

## B. 结果管理
- 批量结果卡片: 删除、替换重生成、下载按钮
- `POST /api/v1/images/generate-batch/retry` — 单张重生成

## C. 生成历史
- `generate-batch` 结果入库 AssetService
- 历史卡片加 platform/topic 标签 + 跳转按钮
- URL: `/image-gen?tab=multi&topic=xxx&platforms=xhs,dy`

## D. 批量主题并行
- 多主题提交，任务队列管理

## E. 灵感获取
- 复用 crawler，预留 xhs 平台
