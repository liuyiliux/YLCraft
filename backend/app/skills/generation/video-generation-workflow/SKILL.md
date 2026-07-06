---
name: video_generation_workflow
title: 视频生成工作流
description: 根据脚本、分镜、参考图或图片资产生成视频任务，并跟踪任务状态。
version: 1.0.0
skill_type: workflow
category: generation
tags: [video, generation, async-task, asset]
triggers:
  keywords: [视频生成, 生成视频, AI视频, 图生视频, 文生视频]
  context_keys: [video_task_id, storyboard_id, asset_id]
  tools: [list_video_backends, generate_video_asset, poll_video_generation_task]
requires_tools: [generate_video_asset]
risk: write
---

# 视频生成工作流

## When To Use

用户要从文本、分镜、图片或参考图生成视频，并需要任务轮询和结果入库时使用。

## Procedure

1. 先确认输入资产、时长、画面运动、镜头目标和模型后端。
2. 生成任务要记录成本提示、任务 ID、轮询方式、产物路径和素材血缘。
3. 输出视频后建议是否进入字幕、BGM、剪辑或发布质检。
4. 异步失败时返回后端错误、请求摘要和可重试参数。

## Verification

检查视频任务是否可追踪，结果是否绑定素材库和项目对象。
