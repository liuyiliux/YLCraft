# Spec: 多平台生图

- `platform_templates` 表存平台模板配置
- `POST /images/generate-outline` 用 LLM 为 topic 生成多平台大纲
- `POST /images/generate-batch` 批量逐页生图
- `GET /images/platform-templates` 列出可用平台
- 前端"多平台生图"Tab：主题输入 → 选平台 → LLM 大纲 → 编辑 → 批量生成 → 分组展示
- 预置 小红书/抖音/微信/头条 4 个平台模板
