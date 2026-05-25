# Proposal: 多平台生图模式

## What

新增"多平台生图"功能：输入一个主题，LLM 拆分为多平台适配提示词，批量生成各平台版本图片。

借鉴 yiliu/yiliu 的设计思想，适配 YLCraft 现有架构。

## Why

- 当前只有单图生成（`n` batch 变体），无法做多平台内容适配
- 创作者需要在不同平台发布同一主题的不同风格内容
- 手动为每个平台写提示词低效

## What changes

| 层 | 新增 |
|---|------|
| **DB** | `platform_templates` 表 — 平台模板配置 |
| **Backend** | `POST /images/generate-outline` — LLM 分析 topic 生成大纲 |
| **Backend** | `POST /images/generate-batch` — 批量生图 |
| **Backend** | `GET /images/platform-templates` — 模板列表 |
| **Frontend** | image-gen 新增"多平台生图"Tab |
| **Seed** | Alembic migration + 预置 5 个平台模板 |
