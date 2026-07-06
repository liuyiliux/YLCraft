---
name: asset_search
title: 素材检索
description: 检索素材库，优先找到可直接复用的图片、视频、音频和项目资产。
version: 1.0.0
skill_type: workflow
category: assets
tags: [asset, search, reuse]
triggers:
  keywords: [素材, 搜索素材, 找图, 找视频, 资产, 素材库]
  context_keys: [project_id, asset_id, character_id]
  tools: [search_assets, semantic_search_assets, search_platform_sources]
requires_tools: [search_assets]
risk: read
---

# 素材检索

## When To Use

用户要找已有素材、复用参考图、查图片/视频/音频资产或避免重复生成时使用。

## Procedure

1. 先从项目绑定资产和当前对象关联资产开始。
2. 再按类型、标签、来源、状态、关键词扩大范围。
3. 返回结果时说明每个素材为什么匹配，以及还缺哪类素材。
4. 如果素材可直接用于生成、剪辑或电子书，说明后续可接入的工具。

## Verification

检查是否优先复用已有资产，是否明确缺口和下一步动作。
