---
name: creative_project_advance
title: 创作项目推进
description: 检查创作项目缺口，并按大纲、角色、章节、正文、脚本、分镜、参考图的顺序推进。
version: 1.0.0
skill_type: workflow
category: creative
tags: [creative-project, outline, chapter, storyboard]
triggers:
  keywords: [创作项目, 项目, 大纲, 章节, 正文, 脚本, 推进, 缺口]
  context_keys: [project_id, creative_project_id, default_project_id, creative_project_context]
  tools: [inspect_creative_project, run_creative_project_pipeline, build_creative_project_context_pack]
requires_tools: [inspect_creative_project]
risk: read
---

# 创作项目推进

## When To Use

用户要求继续项目、检查项目进度、补缺口、推进小说/短剧/漫画项目时使用。

## Procedure

1. 先读取项目上下文和已有内容，判断当前目标。
2. 按依赖链检查缺口：项目大纲、角色库、章节规划、单章细纲、正文、脚本、分镜、参考图匹配。
3. 优先补齐会阻塞后续步骤的结构性内容。
4. 生成或修改内容后说明写入了什么、还缺什么、下一步建议调用哪个工具。
5. 不要跳过版本记录，不要覆盖用户已确认内容。

## Verification

输出前检查：本轮目标是否完成、是否产生可追踪内容、是否留下下一步可执行动作。
