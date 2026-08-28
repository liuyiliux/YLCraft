---
name: portrait_prompt
title: 角色立绘提示词
description: 把角色卡转换为单人立绘、16:9 角色设定板、九宫格动作参考或多角度参考图提示词。
version: 1.0.0
skill_type: prompt
category: creative
tags: [character, portrait, prompt, image-generation]
triggers:
  keywords: [立绘, 角色设定板, 身份板, 九宫格, 表情包, 动作姿势, 姿势, 头像, 角色图, 参考图]
  context_keys: [character_id]
  tools: [preview_character_portrait_prompt, generate_image_asset]
requires_tools: [preview_character_portrait_prompt]
risk: read
---

# 角色立绘提示词

## When To Use

用户要生成角色立绘、身份板、表情包、动作姿势、多视图或图像模型提示词时使用。

## Procedure

1. 先保证单人、清晰五官、统一服装、干净背景和角色身份一致。
2. `character_sheet_16_9` 设定板采用左侧约 34% 半身主立绘、右侧三视图和少量细节条；身份版强调核心外貌和服装；表情包强调同脸同发型同服装下的表情变化；动作姿势强调身体动态和可切割构图。
3. 九宫格或多视图提示词必须写清 same character、same face、same hairstyle、same outfit。
4. 根据模型倾向补充画风和负面约束，避免跑到真人、3D 或过度写实。
5. 输出时分为正向提示词、负面提示词、参考图使用说明和切图建议。

## Verification

检查提示词是否足够稳定，是否避免多人、换脸、换服装、背景过重和构图不可切割。
