---
name: comic_image_prompt
title: 漫画生图提示词
description: 把分镜和参考图组合成可发给图像模型的漫画生图提示词。
version: 1.0.0
skill_type: prompt
category: creative
tags: [comic, image-prompt, storyboard, reference]
triggers:
  keywords: [漫画, 生图提示词, 图片提示词, 画面提示, 镜头图]
  context_keys: [storyboard_id, image_prompt_context]
  tools: [generate_image_asset, preview_image_generation_request]
requires_tools: [preview_image_generation_request]
risk: read
---

# 漫画生图提示词

## When To Use

用户要把分镜、角色卡和参考图转为图像模型可执行提示词时使用。

## Procedure

1. 提示词由剧情画面、角色一致性、参考图用途、构图、镜头、光线、画风和负面约束组成。
2. 如果有角色或背景参考图，明确用途：锁脸、服装、场景结构、色调或画风。
3. 不要只写一句剧情摘要，必须让模型知道谁在画面中、在哪里、做什么、情绪是什么、镜头如何观看。
4. 对连续漫画页要保留统一画风和角色一致性描述。

## Verification

检查提示词是否可直接发送给生图后端，是否包含必要负面约束。
