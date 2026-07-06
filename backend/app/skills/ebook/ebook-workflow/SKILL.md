---
name: ebook_workflow
title: 电子书工作流
description: 从本地文档或文件夹创建电子书，检查章节、封面、元数据和导出状态。
version: 1.0.0
skill_type: workflow
category: ebook
tags: [ebook, epub, export, reader]
triggers:
  keywords: [电子书, epub, mobi, 小说导出, 书籍]
  context_keys: [ebook_task_id, reader_file_id]
  tools: [create_ebook_from_folder, get_ebook_task]
requires_tools: [create_ebook_from_folder]
risk: write
---

# 电子书工作流

## When To Use

用户要从本地文件夹、下载内容或小说项目创建 EPUB/MOBI/HTML 电子书时使用。

## Procedure

1. 确认来源目录、章节规则、封面、标题作者和目标格式。
2. 创建任务后跟踪状态，输出可下载文件和质检问题。
3. 如果用于内置阅读器，说明导入、封面、图片资源和删除管理入口。

## Verification

检查章节、图片、封面、元数据和阅读器可打开性。
