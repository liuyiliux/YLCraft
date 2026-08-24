---
name: novel_completion
title: 小说正文补完
description: 补完或重写小说章节正文，让文本更自然、有节奏，并保持前后连续。
version: 1.0.0
skill_type: workflow
category: novel
tags: [novel, chapter, prose, writer-room]
triggers:
  keywords: [小说, 正文, 章节, 补完, 续写, 重写, 润色]
  context_keys: [novel_id, chapter_id, creative_project_context]
  tools: [run_creative_writer_room, list_novel_bookshelf, preview_novel_chapter]
requires_tools: [run_creative_writer_room]
risk: write
creative:
  capability_roles: [script-writer]
  compatible_project_types: [novel]
  compatible_genres: ["*"]
  stages: [novel_body, prose_draft, prose_rewrite, directed_rewrite]
  context_contribution: "按章节契约推进场景、行动与选择；保留已确认事件和人物关系，不用总结替代戏剧过程。"
  input_schema: {chapter_contract: object, approved_prose: string, narrative_context: string}
  output_schema: {candidate_prose: string, source_content_id: string}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: true
---

# 小说正文补完

## When To Use

用户要求续写、补完、重写或完善小说章节正文时使用。

## Procedure

1. 写正文前读取项目大纲、章节细纲、角色设定、上一章结尾和本章目标。
2. 正文按场景推进，动作、对白、心理和环境交替出现，少解释，多让人物通过选择表现性格。
3. 补完时延续原文语气；重写时保留关键事件、角色关系和伏笔，只改善节奏、细节和可读性。
4. 输出前说明本轮覆盖的章节范围、写入状态和仍需人工确认的点。

## Verification

检查本章目标是否完成、人物动机是否清楚、结尾是否有继续阅读的牵引。
