---
name: prose_review
title: 小说正文审稿
description: 审稿章节正文，指出连贯性、人物动机、节奏和可改写位置。
version: 1.0.0
skill_type: prompt
category: novel
tags: [novel, review, continuity, rewrite]
triggers:
  keywords: [审稿, review, 检查正文, 问题, 改写建议]
  context_keys: [chapter_id, prose_text]
  tools: [run_creative_writer_room]
requires_tools: [run_creative_writer_room]
risk: read
---

# 小说正文审稿

## When To Use

用户要检查章节正文质量、找问题、给出可执行改写建议时使用。

## Procedure

1. 按四类给结论：连续性问题、人物动机问题、节奏问题、可直接改写的句段。
2. 每条问题说明影响和建议，不要泛泛评价。
3. 若文本可用，明确哪些部分应该保留。
4. 给出优先级，先修会影响后续剧情的硬问题。

## Verification

检查建议是否能直接指导改写，而不是只有主观评价。
