---
name: character_visual_card
title: 角色视觉卡
description: 把角色设定补成可复用的视觉卡，服务立绘、漫画分镜和参考图一致性。
version: 1.0.0
skill_type: workflow
category: creative
tags: [character, portrait, visual-card, consistency]
triggers:
  keywords: [角色, 人物, 立绘, 外貌, 视觉卡, 人设]
  context_keys: [character_id]
  tools: [inspect_character, update_character_visual_profile, preview_character_portrait_prompt]
requires_tools: [inspect_character]
risk: write
---

# 角色视觉卡

## When To Use

用户要完善角色外貌、人设视觉规范、立绘一致性、跨项目复用角色时使用。

## Procedure

1. 先整合角色身份、剧情作用、性格、年龄、阵营、已有外貌、参考图和禁忌风格。
2. 输出脸部识别点、发型、眼睛、肤色、体型比例、服装结构、材质、配饰、标志物、色板和画风。
3. 给出一致性规则、负面约束、主立绘提示词、参考图提示词。
4. 如果已有参考图，说明沿用哪些视觉特征，不要凭空重设角色。
5. 区分身份版、表情/动作、多视图：身份版定义核心视觉，其他视图只扩展表现。

## Verification

检查视觉卡是否能让不同模型、不同场景复现同一角色。
