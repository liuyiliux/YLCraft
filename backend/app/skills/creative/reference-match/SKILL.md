---
name: reference_match
title: 参考图匹配
description: 根据脚本、分镜或角色卡，匹配素材库里的角色、背景、道具和风格参考图。
version: 1.0.0
skill_type: workflow
category: creative
tags: [reference, asset, matching, consistency]
triggers:
  keywords: [参考图, 匹配, 一致性, 素材匹配, 复用]
  context_keys: [project_id, character_id, storyboard_id]
  tools: [match_creative_project_reference_assets, search_assets, semantic_search_assets]
requires_tools: [match_creative_project_reference_assets]
risk: read
---

# 参考图匹配

## When To Use

用户要为角色、分镜、漫画图或视频镜头找可复用参考图时使用。

## Procedure

1. 先列出本镜头需要稳定的元素：角色脸、服装、背景、道具、画风。
2. 优先使用已绑定到项目、角色或同章节的素材。
3. 其次用标签、来源、风格和文本相似度检索。
4. 输出每个参考图的 asset_id、用途、使用权重和备注。
5. 找不到时明确建议新生成哪类参考图。

## Verification

检查匹配结果是否能降低角色漂移、场景漂移和画风漂移。
