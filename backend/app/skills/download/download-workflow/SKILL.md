---
name: download_workflow
title: 下载工作流
description: 解析链接、磁力、网盘或平台地址，创建下载任务，并把下载结果纳入素材库。
version: 1.0.0
skill_type: workflow
category: download
tags: [download, magnet, link, asset]
triggers:
  keywords: [下载, 解析链接, 磁力, 网盘, 链接, 去水印]
  context_keys: [download_url, asset_url]
  tools: [parse_download_link, create_download_task, fetch_platform_no_watermark]
requires_tools: [parse_download_link]
risk: write
---

# 下载工作流

## When To Use

用户要解析链接、下载素材、处理磁力/网盘/平台地址、去水印或入库下载结果时使用。

## Procedure

1. 下载前判断链接类型、资源来源、是否需要外部访问或账号能力。
2. 涉及写入、消耗型任务或版权风险时先说明影响。
3. 创建任务后记录任务 ID、保存路径、素材入库状态和失败原因。
4. 下载完成后建议是否进入素材打标、剪辑、电子书或阅读器流程。

## Verification

检查是否能追踪任务状态、文件路径和入库结果。
