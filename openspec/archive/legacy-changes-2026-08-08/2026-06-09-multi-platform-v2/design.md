# Design: 多平台生图 V2

## Task A: 在线配置平台模板
- **页面**: `/settings` 或独立 `/platform-templates` 页
- **功能**: CRUD 管理 `platform_templates` 表
- **字段**: platform, name, outline_template, image_template, video_template, default_size, is_active, sort_order
- **后端**: 复用已有 DB 模型，加 PUT/DELETE 端点

## Task B: 结果管理
- **功能**: 批量结果中删除单张、替换重生成、下载
- **前端**: MultiPlatformGen 结果区加操作按钮
- **后端**: 复用 `generate-batch` 单张重生成

## Task C: 生成历史优化
- **入库**: `generate-batch` 结果走 AssetService 统一入库
- **字段**: platform, template_id, topic, 大纲信息
- **跳转**: 历史卡片加"跳到多平台生成"按钮

## Task D: 批量主题并行（往后排）
- 多主题同时提交，每主题按多平台生成
- 需要任务队列支持

## Task E: 灵感获取（往后排）
- 复用 crawler 模块
- 小红书平台预留给后续实现
