# 2026-08-14 示例配置与图生 3D 进度

## 当前框架

- 前端：`frontend/src/pages/settings/index.tsx` 承载设置页 Tab；`provider-presets` 从 `examples/ai-connectors/*.json` 读取公开示例。
- API：`POST /api/v1/ai/connectors` 创建连接器，`PUT /api/v1/ai/connectors/{id}` 更新连接器，`POST /api/v1/ai/connectors/import` 批量导入。
- 数据模型：`ai_connectors.provider_type` 使用 PostgreSQL `aiprovidertype` 枚举；图生 3D 的持久化值是 `3d`。
- 3D 执行：通用 HTTP 连接器负责请求模板、响应 JSONPath 和轮询；腾讯混元预设位于 `examples/ai-connectors/tencent-hunyuan-3d-pro.json`。

## 已完成

- 示例配置页改为类型筛选、搜索和摘要卡片；请求模板、响应配置和完整 JSON 放入详情抽屉。
- 一键填入会创建停用的独立连接器，不覆盖用户已有配置，也不会带入 API Key。
- 前后端均兼容历史类型值 `model3d`、`model_3d`、`image_to_3d`、`image-to-3d`，统一保存为 `3d`。
- 增加图生 3D 类型归一化回归测试；前端构建和 focused 测试已通过。

## 当前注意事项

- 修改后端代码后必须重启正在运行的后端进程；旧进程仍会继续报 `invalid input value for enum aiprovidertype: "model3d"`。
- 公开示例是配置模板，不代表已经配置真实域名、模型或认证头；导入后需在连接器详情补齐并启用。

## 下一步

- 重启服务后手工验证图生 3D 示例一键填入和数据库落库。
- 对示例页做深色主题可读性检查，并补充 API 文档中的类型兼容说明。
- 继续完善任务中心与 AI 调用日志的请求、响应、轮询和失败诊断关联。
