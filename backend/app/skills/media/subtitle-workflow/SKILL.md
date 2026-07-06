---
name: subtitle_workflow
title: 字幕工作流
description: 提取、编辑、样式化或烧录字幕，服务短剧、解说、剪辑和发布流程。
version: 1.0.0
skill_type: workflow
category: media
tags: [subtitle, video, publish]
triggers:
  keywords: [字幕, 提取字幕, 烧录字幕, 字幕样式]
  context_keys: [video_id, subtitle_id]
  tools: [extract_subtitle, get_subtitle_styles, burn_subtitle]
requires_tools: [extract_subtitle]
risk: write
---

# 字幕工作流

## When To Use

用户要提取字幕、编辑字幕、设置样式或把字幕烧录到视频时使用。

## Procedure

1. 先确认视频来源、语言、输出格式、是否烧录以及字幕样式。
2. 提取和烧录属于任务型操作，要返回任务状态、输出文件和可继续操作。
3. 与短剧/解说剪辑联动时，保留时间轴和片段对应关系。

## Verification

检查字幕文件、视频输出和后续剪辑流程是否可衔接。
