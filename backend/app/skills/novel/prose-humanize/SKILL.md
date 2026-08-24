---
name: prose_humanize
title: 正文去 AI 腔
description: 降低 AI 腔，增加具体动作、潜台词、停顿和生活细节。
version: 1.0.0
skill_type: prompt
category: novel
tags: [novel, prose, rewrite, humanize]
triggers:
  keywords: [自然, 人味, AI腔, 润色, 对白, 节奏]
  context_keys: [chapter_id, prose_text]
  tools: [run_creative_writer_room]
requires_tools: [run_creative_writer_room]
risk: write
creative:
  capability_roles: [script-writer]
  compatible_project_types: [novel]
  compatible_genres: ["*"]
  stages: [prose_humanized, humanized_prose, prose_rewrite, directed_rewrite]
  context_contribution: "用动作、感官细节、潜台词与节奏变化降低概念化表达；保持原事件顺序和人物动机。"
  input_schema: {source_prose: string, narrative_context: string}
  output_schema: {candidate_prose: string, source_content_id: string}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: true
---

# 正文去 AI 腔

## When To Use

用户觉得文字机械、概念化、像 AI 写的，要求润色成人味更强的小说正文时使用。

## Procedure

1. 不要只替换同义词，优先删除概念化总结。
2. 补入可被看见、听见、触摸到的细节。
3. 对白要有遮掩、试探、误会和反应差，不要让人物把动机直接讲完。
4. 保留原事件顺序，控制解释密度，让段落长短有变化。

## Verification

检查修改是否保留剧情信息，同时提升动作、对白、节奏和场景质感。
