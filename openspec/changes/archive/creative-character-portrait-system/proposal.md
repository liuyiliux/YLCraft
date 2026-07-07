# Proposal: Creative Character Portrait System

## What

Build a production-grade character portrait workflow for YLCraft creative projects.

The feature upgrades current single-image portrait generation into a reusable character identity system:

- Structured character visual cards.
- Built-in portrait prompt presets, especially the 16:9 artistic character identity board from `短剧项目参考/立绘提示词.txt`.
- Prompt preview, copy and optional AI optimization.
- Asset Hub versioning for every generated portrait.
- Main portrait selection and locked character appearance.
- Reuse of character card and portrait references in storyboard and comic image generation.

## Why

The current character page can generate a portrait and write it to Asset Hub, but the generation target is still too generic. For short drama, manga and storyboard production, the goal is not just a good-looking image. The goal is a stable reference that future image and video generations can use to preserve:

- Face identity.
- Hair and silhouette.
- Clothing structure.
- Body proportions.
- Pose language.
- Expression range.
- Signature details and forbidden variations.

Without a structured portrait system, downstream storyboard images drift across panels and chapters.

## Goals

- Add a character visual card schema that captures fixed appearance, costume, signature items, expression set, pose set and negative constraints.
- Add preset-based portrait prompt generation:
  - `main_portrait`
  - `multi_view_sheet`
  - `identity_board_16_9`
  - `expression_pack`
  - `action_pose_pack`
  - `transparent_or_white_background`
- Use the reference prompt in `短剧项目参考/立绘提示词.txt` as the design base for `identity_board_16_9`.
- Generate full prompt and negative prompt previews before spending image-generation credits.
- Save every generated portrait as an Asset Hub character node version.
- Let users mark one generated portrait as the main portrait.
- Let storyboard and comic image generation automatically inject the selected character card and main portrait reference, with manual override where needed.

## Non-goals

- Do not build a full 3D blocking editor.
- Do not require a single image model or vendor-specific consistency feature.
- Do not implement full multi-agent character simulation in this change.
- Do not replace the existing character CRUD page; evolve it incrementally.
- Do not guarantee perfect cross-model identity consistency; store references and prompts so compatible providers can use them.

## User Value

- A user can create or edit a character, generate a reliable identity board, set it as the main reference, and later reuse it in storyboards.
- A user can inspect exactly which character card and portrait version were used to generate a panel.
- A user can regenerate portrait versions without losing prior good versions.

## Relationship to roadmap

This change implements the character portrait part of `creative-project-optimization-roadmap` Phase 1 and should remain compatible with future reference-card, storyboard prompt v2 and canvas work.
