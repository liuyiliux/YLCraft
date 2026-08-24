---
name: image_generation_workflow
title: 图片生成工作流
description: 根据项目、角色、分镜和参考图生成图片请求，保存结果、任务和素材血缘。
version: 1.0.0
skill_type: workflow
category: generation
tags: [image, generation, async-task, asset]
triggers:
  keywords: [生图, 生成图片, AI图片, 参考图, 立绘, 漫画图]
  context_keys: [image_task_id, character_id, storyboard_id]
  tools: [preview_image_generation_request, generate_image_asset, poll_image_generation_task]
requires_tools: [preview_image_generation_request, generate_image_asset]
risk: write
creative:
  capability_roles: [image-producer]
  compatible_project_types: [short_drama, novel, manga, mixed]
  compatible_genres: ["*"]
  stages: [image, image_set, visual_reference, platform_image]
  context_contribution: "图片生成前保留意图、参考资产、提示词、负面提示词、供应商、模型、尺寸和预期产物；实际生成必须等待确认。"
  input_schema: {planning_summary: object, reference_asset_ids: array, provider: string, model: string}
  output_schema: {task_id: string, asset_ids: array, diagnostics: object}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: false
---

# 图片生成工作流

## When To Use

用户要生成图片、测试生图模型、用参考图生成立绘/漫画图、跟踪异步生图任务时使用。

## Procedure

1. 生图前读取项目、角色、分镜和参考图上下文，明确主体、画风、尺寸、负面约束和参考图用途。
2. 先预览请求摘要，成本型或异步任务再执行生成。
3. 生成后展示任务状态、结果路径、素材入库状态和 lineage。
4. 对异步后端要说明轮询方式、任务 ID、失败诊断和重试入口。

## Verification

检查图片结果是否可追踪、是否绑定到项目/角色/分镜，是否记录模型和提示词。
