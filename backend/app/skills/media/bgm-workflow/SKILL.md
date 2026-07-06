---
name: bgm_workflow
title: BGM 工作流
description: 检索、上传、选择或混入 BGM，服务剪辑、短剧和发布成片。
version: 1.0.0
skill_type: workflow
category: media
tags: [bgm, audio, video, publish]
triggers:
  keywords: [BGM, 背景音乐, 配乐, 混音, 音乐]
  context_keys: [video_id, audio_id]
  tools: [list_bgm_tracks, add_bgm_to_video, upload_bgm]
requires_tools: [list_bgm_tracks]
risk: write
---

# BGM 工作流

## When To Use

用户要找配乐、上传音乐、给视频混入 BGM 或调整音量时使用。

## Procedure

1. BGM 选择要结合场景情绪、节奏、时长和授权状态。
2. 混音或添加到视频前确认输入视频、音轨、音量和输出路径。
3. 输出时说明使用的音频素材、视频产物和授权风险。

## Verification

检查音量、时长、授权和输出路径是否清楚。
