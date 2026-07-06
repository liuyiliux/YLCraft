---
name: provider_setup
title: AI 模型供应商配置
description: 根据供应商文档、curl 示例或 API 规范创建模型连接器，并测试文本、生图和图片编辑能力。
version: 1.0.0
skill_type: workflow
category: ai-config
tags: [ai-provider, connector, model, image-edit]
triggers:
  keywords: [模型配置, 供应商, connector, api key, curl, 生图模型, 图片编辑]
  context_keys: [provider_id, model_provider, ai_connector_context]
  tools: [create_ai_provider_spec, update_ai_provider_spec, test_ai_connector]
requires_tools: [test_ai_connector]
risk: write
---

# AI 模型供应商配置

## When To Use

用户提供任意供应商规范、curl 示例、API 文档或要求测试模型连接器时使用。

## Procedure

1. 先从文档或 curl 中抽取 base URL、鉴权方式、路径、请求体、响应格式和异步规则。
2. 不要把示例供应商硬编码为默认模型；只把它当作通用配置能力的测试样例。
3. 对图片编辑区分公网图片 JSON、本地文件 multipart、返回 URL 或 b64_json。
4. 测试时输出请求摘要、响应摘要、错误诊断和下一步修复建议。
5. 写入前尽量生成草稿并让用户确认关键字段。

## Verification

检查连接器是否能独立测试，是否不会覆盖用户已有 provider/model 偏好。
