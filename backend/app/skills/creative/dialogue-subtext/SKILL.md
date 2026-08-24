---
name: dialogue_subtext
title: 对白潜台词与人物声音
description: 让对白保留冲突、遮掩和人物差异，减少直白说明和 AI 腔。
version: 1.0.0
skill_type: prompt
category: creative-writing
tags: [dialogue, subtext, character, prose, short_drama]
triggers:
  keywords: [对白, 潜台词, 人物声音, 台词自然, AI腔]
  context_keys: [chapter_id, prose_text, creative_project_context]
  tools: [run_creative_writer_room]
requires_tools: [run_creative_writer_room]
risk: read
creative:
  capability_roles: [script-writer]
  compatible_project_types: [short_drama, novel, comic]
  compatible_genres: ["*"]
  stages: [novel_body, prose_humanized, humanized_prose, prose_rewrite, directed_rewrite]
  context_contribution: "对白优先呈现人物当下想要什么、害怕什么和不愿说什么；用停顿、动作、错答和称呼变化承载潜台词，保持事件顺序与人物动机不变。"
  input_schema: {source_prose: string, character_context: string}
  output_schema: {candidate_prose: string, dialogue_notes: array}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: false
---

# 对白潜台词与人物声音

1. 删除角色已经知道、却被迫重复说明的内容。
2. 每段对白至少保留一个没有说出口的目的或情绪。
3. 通过动作、停顿、打断和称呼变化区分人物，而不是只改词汇。
4. 改写后核对剧情事实、人物关系和前后事件顺序。
