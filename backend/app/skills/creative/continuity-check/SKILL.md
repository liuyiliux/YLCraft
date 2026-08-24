---
name: continuity_check
title: 连续性与事实守门
description: 在生成或审稿前检查章节与项目大纲、角色关系、前文事实是否冲突。
version: 1.0.0
skill_type: prompt
category: creative-writing
tags: [continuity, canon, review, writing-guardrail]
triggers:
  keywords: [连续性, 事实检查, 人物关系, 设定冲突, 审稿]
  context_keys: [creative_project_context, chapter_contract, prose_text]
  tools: [run_creative_writer_room]
requires_tools: [run_creative_writer_room]
risk: read
creative:
  capability_roles: [editorial-reviewer]
  compatible_project_types: [short_drama, novel, comic]
  compatible_genres: ["*"]
  stages: [chapter_outline, novel_body, prose_review, prose_rewrite, directed_rewrite]
  context_contribution: "把项目大纲、章节契约和已确认事实作为只读约束，优先标出硬冲突、人物动机断裂和伏笔状态错误，再给出最小修复建议。"
  input_schema: {candidate_prose: string, narrative_context: string, chapter_contract: object}
  output_schema: {issues: array, severity: string, repair_plan: array}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger, foreshadowing_status]
  auto_apply: false
---

# 连续性与事实守门

1. 先检查硬事实和人物关系，再检查节奏与表达。
2. 每个问题都指出来源事实、冲突位置和最小修复方式。
3. 不把推测写回正式正文、项目圣经或事实台账。
4. 没有问题时明确说明可保留的段落和仍需人工确认的风险。
