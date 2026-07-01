# Tasks

## Phase 1: Visual Card Contract

- [ ] 1.1 Define the character visual profile schema and decide first storage location (`visual_profile_json` column or metadata-compatible fallback).
- [ ] 1.2 Add backend helpers to synthesize a visual profile from existing `Character` fields.
- [ ] 1.3 Add validation and normalization for visual tags, signature items, expression set, pose set and negative constraints.
- [ ] 1.4 Add migration/backfill behavior that leaves existing characters valid.

## Phase 2: Prompt Presets

- [ ] 2.1 Implement backend prompt builder for `main_portrait`.
- [ ] 2.2 Implement backend prompt builder for `multi_view_sheet`.
- [ ] 2.3 Implement backend prompt builder for `identity_board_16_9` using `短剧项目参考/立绘提示词.txt` as the preset baseline.
- [ ] 2.4 Implement backend prompt builder for `expression_pack`.
- [ ] 2.5 Implement backend prompt builder for `action_pose_pack`.
- [ ] 2.6 Implement backend prompt builder/output option for `transparent_or_white_background`.
- [ ] 2.7 Keep `expression_pose_sheet` as a compatibility alias or combined preset.
- [ ] 2.8 Add `POST /api/v1/characters/{id}/portrait/prompt-preview`.
- [ ] 2.9 Add tests for prompt rendering, negative constraints and fallback from existing character fields.

## Phase 3: Portrait Generation and Versioning

- [ ] 3.1 Extend portrait generation request with `preset`, `visual_profile`, `style_override`, `negative_override` and `set_as_main`.
- [ ] 3.2 Store preset, prompt template version and visual profile snapshot in Asset Hub version params.
- [ ] 3.3 Store generated representations with preset and main-selection metadata.
- [ ] 3.4 Add endpoint to mark an existing portrait version as main.
- [ ] 3.5 Add tests for Asset Hub metadata, main portrait selection and version preservation.

## Phase 4: Frontend Character Page

- [ ] 4.1 Add visual card editing controls to the character form/drawer.
- [ ] 4.2 Add portrait preset segmented control for 主立绘、多视图设定板、16:9 身份板、表情包、动作姿态、透明底/白底.
- [ ] 4.3 Add prompt preview, copy and optimize flow backed by the prompt-preview endpoint.
- [ ] 4.4 Add portrait version list with preset/model/time and set-main action.
- [ ] 4.5 Preserve existing quick generation behavior for users who only fill appearance/costume.

## Phase 5: Creative Project Integration

- [ ] 5.1 Make project storyboard/comic image prompt generation read character visual profiles.
- [ ] 5.2 When supported by the selected backend, pass main portrait image as a reference image.
- [ ] 5.3 Add manual per-panel reference override.
- [ ] 5.4 Record character and portrait Asset Hub lineage on generated panel images.
- [ ] 5.5 Add tests for prompt injection and lineage metadata.

## Verification

- [ ] 6.1 Verify existing characters without visual profiles can still generate portraits.
- [ ] 6.2 Verify `identity_board_16_9` prompt includes layout, no-overlap, face anchor, multi-view, expression and detail study rules.
- [ ] 6.3 Verify each preset maps to the expected output intent: main portrait, multi-view sheet, identity board, expression pack, action pose pack and transparent/white-background material.
- [ ] 6.4 Verify generated portrait versions remain visible in Asset Hub and one can be selected as main.
- [ ] 6.5 Verify a storyboard panel prompt includes linked character profile and portrait reference information.
- [ ] 6.6 Run backend tests and frontend build for changed areas.
