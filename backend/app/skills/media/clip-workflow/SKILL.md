---
name: clip_workflow
title: 剪辑工作流
description: 调用剪辑引擎执行智能剪辑、解说视频处理、字幕/音频/片段组合。
version: 1.0.0
skill_type: workflow
category: media
tags: [clip, video, editing, task]
triggers:
  keywords: [剪辑, 混剪, 成片, 切片, 解说视频]
  context_keys: [video_id, clip_task_id]
  tools: [start_cutclaw_clip, start_narrato_clip, start_moe_clip, get_clip_task_status]
requires_tools: [start_cutclaw_clip]
risk: write
---

# 剪辑工作流

## When To Use

用户要自动剪辑、解说视频处理、混剪、生成成片或跟踪剪辑任务时使用。

## Procedure

1. 剪辑前确认源视频、脚本、字幕、目标时长、剪辑引擎和输出格式。
2. 任务启动后跟踪状态，并把输出文件和素材库/项目关联起来。
3. 如果需要字幕、BGM 或 TTS，说明前置依赖是否已满足。

## Verification

检查任务状态、输出文件、素材绑定和失败诊断是否完整。
