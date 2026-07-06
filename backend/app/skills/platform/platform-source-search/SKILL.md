---
name: platform_source_search
title: 外部平台搜索
description: 搜索 B站、小红书、抖音、快手、微博、知乎、公众号等外部平台，并把结果用于素材或项目推进。
version: 1.0.0
skill_type: workflow
category: platform
tags: [platform, search, crawler, asset]
triggers:
  keywords: [平台, B站, 小红书, 抖音, 快手, 微博, 知乎, 公众号, 外部搜索, 搜视频]
  context_keys: [platform, crawler_context]
  tools: [search_platform_sources, search_platform_sources_enhanced, get_platform_note_detail]
requires_tools: [search_platform_sources]
risk: network
---

# 外部平台搜索

## When To Use

用户要联网搜索平台内容、找参考素材、抓详情、把平台结果导入素材库时使用。

## Procedure

1. 先确认平台、关键词、搜索类型和最大结果数。
2. 如果用户只补充平台或关键词，继承当前对话上下文。
3. 搜索后总结命中数量、可用结果、账号/登录限制和下一步抓取建议。
4. 导入素材库前说明来源、版权/授权风险和可关联的项目对象。

## Verification

检查是否说明平台限制，是否把搜索结果转成可执行的素材/项目动作。
