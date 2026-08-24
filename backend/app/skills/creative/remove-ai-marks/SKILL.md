---
name: remove_ai_marks
title: AI 来源标记与文件元数据清理
description: 审计并为用户拥有或获授权的图片、文本生成不覆盖原文件的清理副本。
version: 1.0.0
skill_type: workflow
category: creative
tags: [provenance, metadata, asset-hub]
triggers:
  keywords: [去 AI 标记, 清理元数据, EXIF, XMP, C2PA, 隐形字符]
  tools: [clean_asset_provenance]
requires_tools: [clean_asset_provenance]
risk: costly
---

# AI 来源标记与文件元数据清理

只处理用户拥有或明确获授权的资产。先展示审计结果，再在用户确认后生成派生副本；原资产永不覆盖。

当前内置适配器支持文本隐形/双向控制符和常见图片 EXIF/格式元数据清理。未支持的格式只能审计，不能宣称已清理视觉水印。结果必须回流 Asset Hub，并保留 `derived_from` 血缘和操作诊断。
