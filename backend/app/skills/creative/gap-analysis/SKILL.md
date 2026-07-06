---
name: gap_analysis
title: 项目缺口分析
description: 识别项目当前缺口，并按影响后续生产的优先级排序。
version: 1.0.0
skill_type: workflow
category: creative
tags: [gap, audit, project, planning]
triggers:
  keywords: [缺口, 还缺, 下一步, 检查, 完成情况]
  context_keys: [creative_project_context]
  tools: [inspect_creative_project, list_creative_project_contents]
requires_tools: [inspect_creative_project]
risk: read
---

# 项目缺口分析

## When To Use

用户问当前项目还缺什么、下一步做什么、哪些内容阻塞后续生产时使用。

## Procedure

1. 先判断当前目标，再检查依赖链：大纲、角色、章节、正文、脚本、分镜、参考图、图片产物。
2. 不要只列清单，要说明每个缺口阻塞了哪个后续动作。
3. 按优先级输出：必须先做、可以并行、可延后。
4. 给出下一步建议调用的工具或工作流。

## Verification

检查建议是否能直接变成下一轮任务。
