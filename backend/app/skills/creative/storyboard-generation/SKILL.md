---
name: storyboard_generation
title: 分镜生成
description: 把章节正文或脚本拆成镜头分镜，包含画面、台词、情绪、场景作用和生图提示词。
version: 1.0.0
skill_type: workflow
category: creative
tags: [storyboard, comic, script, shot]
triggers:
  keywords: [分镜, 镜头, 漫画, 脚本转分镜, 画面]
  context_keys: [chapter_id, script_id, storyboard_id]
  tools: [generate_storyboard, list_creative_project_contents, update_creative_project_content]
requires_tools: [generate_storyboard]
risk: write
creative:
  capability_roles: [storyboard-director]
  compatible_project_types: [short_drama, novel, manga, mixed]
  compatible_genres: ["*"]
  stages: [page_plan, storyboard, shot_list, image_prompt]
  context_contribution: "将章节目标拆成可拍、可画、可生成的镜头或漫画格，并保留角色、场景、画面目的和参考素材缺口。"
  input_schema: {script_or_prose: string, chapter_context: object, character_context: array}
  output_schema: {storyboard: object, prompt_briefs: array, reference_needs: array}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: false
---

# 分镜生成

## When To Use

用户要把小说正文、短剧脚本或章节内容拆成镜头、漫画页或图像生成计划时使用。

## Procedure

1. 先确认章节目标、场景地点、出场角色、冲突推进和关键台词。
2. 每个镜头包含编号、场景摘要、画面描述、人物动作、情绪、对白/旁白、地点、镜头景别。
3. 标注场景作用、涉及角色 ID、涉及背景/道具参考 ID、可直接生图的提示词和负面约束。
4. 漫画阅读用图应跟随分镜；脚本图可作为镜头预览，不要和最终漫画页混淆。

## Verification

检查分镜是否覆盖剧情推进，并能直接进入参考图匹配和图片生成。
