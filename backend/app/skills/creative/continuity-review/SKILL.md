---
name: continuity_review
title: 连续性检查
description: 检查创作项目的连续性，包括人物、设定、章节事件和视觉一致性。
version: 1.0.0
skill_type: workflow
category: creative
tags: [continuity, review, project, consistency]
triggers:
  keywords: [连贯, 连续性, 前后, 设定冲突, 一致性, 质检]
  context_keys: [creative_project_context]
  tools: [inspect_creative_project, list_creative_project_contents]
requires_tools: [inspect_creative_project]
risk: read
---

# 连续性检查

## When To Use

用户要检查剧情、人设、视觉资产、章节或项目内容是否前后矛盾时使用。

## Procedure

1. 覆盖人物动机、事件因果、设定约束、伏笔回收和视觉参考一致性。
2. 按严重程度排序，先指出会阻塞后续生产的问题。
3. 每个问题给出证据、影响和可执行修复建议。
4. 对视觉连续性说明冲突素材、冲突字段和建议保留版本。

## Verification

检查输出是否能直接指导修复，而不是只说“有冲突”。
