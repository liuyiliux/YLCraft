---
name: asset_tagging
title: 素材打标
description: 为素材补充类型、风格、来源、状态、角色/项目关联和可检索标签。
version: 1.0.0
skill_type: workflow
category: assets
tags: [asset, tagging, metadata, library]
triggers:
  keywords: [打标, 标签, 分类, 入库, 整理素材]
  context_keys: [asset_id, project_id, character_id]
  tools: [add_asset_tag, import_platform_results_to_assets]
requires_tools: [add_asset_tag]
risk: write
---

# 素材打标

## When To Use

用户导入素材、整理素材库、补标签、关联项目/角色/章节时使用。

## Procedure

1. 区分内容标签、用途标签、风格标签、来源标签和状态标签。
2. 角色立绘、背景、道具、分镜图、漫画图尽量关联到项目、章节、角色或镜头。
3. 如果素材来自平台或下载任务，保留来源、原链接和授权风险说明。
4. 输出打标结果和仍需人工确认的元数据。

## Verification

检查素材是否能被搜索、复用、追踪来源和绑定业务对象。
