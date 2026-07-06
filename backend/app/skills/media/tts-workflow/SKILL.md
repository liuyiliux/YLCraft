---
name: tts_workflow
title: TTS 配音工作流
description: 把文本转换为语音，选择音色、语速、格式，并保存音频素材。
version: 1.0.0
skill_type: workflow
category: media
tags: [tts, voice, audio, asset]
triggers:
  keywords: [TTS, 配音, 语音, 文字转语音, 音色]
  context_keys: [tts_task_id, audio_id]
  tools: [preview_tts_request, generate_tts_audio]
requires_tools: [preview_tts_request, generate_tts_audio]
risk: write
---

# TTS 配音工作流

## When To Use

用户要把文案、小说片段、解说稿或台词生成语音时使用。

## Procedure

1. 先确认文本、语言、音色、语速、输出格式和用途。
2. 成本型生成前预览请求，生成后返回音频路径、时长和任务状态。
3. 建议是否加入剪辑、字幕或素材库。

## Verification

检查语音文件是否可播放、可追踪、可用于后续视频流程。
