---
name: export_quality_workflow
title: 导出质量检查
description: 导出素材集、项目内容或发布包前做质量检查、去重、合并和格式校验。
version: 1.0.0
skill_type: workflow
category: export
tags: [export, quality, deduplicate, publish]
triggers:
  keywords: [导出, 质检, 去重, 重复素材, 数据集, 发布包]
  context_keys: [export_task_id, asset_dataset_id]
  tools: [export_asset_dataset, find_duplicate_assets, merge_duplicate_assets]
requires_tools: [export_asset_dataset]
risk: write
---

# 导出质量检查

## When To Use

用户要导出素材集、项目包、发布包或进行去重合并前使用。

## Procedure

1. 导出前明确目标平台、格式、素材范围、命名规则和质检标准。
2. 对重复素材、缺失文件、断链血缘和格式错误先报告，再执行写入型导出。
3. 合并或删除前保留来源、引用关系和可回滚信息。

## Verification

检查导出包是否完整、可复现、可追踪，并符合目标格式。
