---
name: episode_hook_rhythm
title: 单集钩子与节奏
description: 为短剧或章节安排开场钩子、冲突升级、信息揭示和结尾悬念。
version: 1.0.0
skill_type: workflow
category: creative-writing
tags: [short_drama, novel, chapter, hook, rhythm]
triggers:
  keywords: [开场钩子, 单集节奏, 反转, 结尾悬念, 追更点]
  context_keys: [creative_project_context, chapter_contract]
  tools: [generate_chapter_outline, generate_novel_body]
requires_tools: [generate_chapter_outline]
risk: read
creative:
  capability_roles: [story-designer]
  compatible_project_types: [short_drama, novel, comic]
  compatible_genres: ["*"]
  stages: [chapter_outline, novel_body, prose_draft, prose_rewrite, directed_rewrite]
  context_contribution: "先给出可拍、可写的节奏骨架：前 10% 抛出具体异常，中段用选择和代价推进，至少一次信息反转，结尾留下明确行动悬念。"
  input_schema: {chapter_contract: object, project_context: string}
  output_schema: {opening_hook: string, escalation_beats: array, reveal: string, ending_hook: string}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: false
---

# 单集钩子与节奏

1. 开场必须出现可见、可听或可执行的异常，不用概念介绍代替事件。
2. 每个节拍都要改变角色选择、关系或风险，避免只有解释。
3. 反转要回收已埋下的信息，不凭空添加新事实。
4. 结尾留下一个具体问题、动作或倒计时，能直接推动下一集。
