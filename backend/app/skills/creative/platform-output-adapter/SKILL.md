---
name: platform_output_adapter
title: 平台输出适配
description: 将已确认的故事、脚本、图片或视频产物适配为平台模板、比例、页面结构、标题和标签建议。
version: 1.0.0
skill_type: workflow
category: creative
tags: [platform, output, xiaohongshu, douyin, layout]
triggers:
  keywords: [平台适配, 小红书封面, 抖音比例, 图文排版, 标题标签, 发布版式]
  context_keys: [project_id, production_plan, platform]
  tools: [list_prompt_templates, get_prompt_template, preview_prompt_template_render]
requires_tools: [list_prompt_templates, preview_prompt_template_render]
risk: read
creative:
  capability_roles: [platform-adapter]
  compatible_project_types: [short_drama, novel, manga, mixed]
  compatible_genres: ["*"]
  stages: [platform_adaptation, layout, platform_image, platform_video, pre_publish_review]
  context_contribution: "复用现有平台模板和图片编辑/多平台生图能力，为目标平台给出比例、页序、标题、正文、标签和导出检查项；不创建平行生产线。"
  input_schema: {platform: string, source_content_ids: array, source_asset_ids: array}
  output_schema: {platform_brief: object, template_id: string, export_checklist: array}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: false
---

# 平台输出适配

1. 先读取用户选择的平台模板和已有成品，不重新生成已确认的故事、角色或分镜。
2. 给出适配后的比例、封面重点、页序或镜头顺序、标题、正文和标签建议。
3. 小红书、抖音、微信等只作为输出适配目标，复用现有多平台生图和图片编辑能力。
4. 发布、下载或再次生成属于外部/消耗型动作，必须单独取得用户确认。
