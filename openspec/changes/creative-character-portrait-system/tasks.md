# Tasks

## Phase 1: Visual Card Contract

- [x] 1.1 Define the character visual profile schema and decide first storage location (`visual_profile_json` column or metadata-compatible fallback).
- [x] 1.2 Add backend helpers to synthesize a visual profile from existing `Character` fields.
- [x] 1.3 Add validation and normalization for visual tags, signature items, expression set, pose set and negative constraints.
- [ ] 1.4 Add migration/backfill behavior that leaves existing characters valid.

## Phase 2: Prompt Presets

- [x] 2.1 Implement backend prompt builder for `main_portrait`.
- [x] 2.2 Implement backend prompt builder for `multi_view_sheet`.
- [x] 2.3 Implement backend prompt builder for `identity_board_16_9` using `短剧项目参考/立绘提示词.txt` as the preset baseline.
- [x] 2.4 Implement backend prompt builder for `expression_pack`.
- [x] 2.5 Implement backend prompt builder for `action_pose_pack`.
- [x] 2.6 Implement backend prompt builder/output option for `transparent_or_white_background`.
- [x] 2.7 Keep `expression_pose_sheet` as a compatibility alias or combined preset.
- [x] 2.8 Add `POST /api/v1/characters/{id}/portrait/prompt-preview`.
- [x] 2.9 Add tests for prompt rendering, negative constraints and fallback from existing character fields.
- [x] 2.10 Add preset-specific negative constraints for identity board, expression, pose and material outputs.
- [x] 2.11 Add `expression_grid_3x3` and `pose_grid_3x3` presets for cutting-friendly grid sheets.
- [x] 2.12 Re-scope `identity_board_16_9` as a summary board instead of a production model sheet.
- [x] 2.13 Add `headshot_icon` and `key_visual` presets for UI portraits and promotional art.

## Phase 3: Portrait Generation and Versioning

- [x] 3.1 Extend portrait generation request with `preset`, `visual_profile`, `style_override`, `negative_override` and `set_as_main`.
- [x] 3.2 Store preset, prompt template version and visual profile snapshot in Asset Hub version params.
- [x] 3.3 Store generated representations with preset and main-selection metadata.
- [x] 3.4 Add endpoint to mark an existing portrait version as main.
- [x] 3.5 Add tests for Asset Hub metadata, main portrait selection and version preservation.
- [x] 3.6 Add endpoint to slice expression/pose grid portrait versions into child Asset Hub image nodes.

## Phase 4: Frontend Character Page

- [x] 4.1 Add visual card editing controls to the character form/drawer.
- [x] 4.2 Add portrait preset segmented control for 主立绘、多视图设定板、16:9 身份板、表情包、动作姿态、透明底/白底.
- [x] 4.3 Add prompt preview, copy and optimize flow backed by the prompt-preview endpoint.
- [x] 4.6 Add expression grid and pose grid preset choices.
- [x] 4.7 Add headshot and Key Visual preset choices.
- [x] 4.9 Add frontend action to cut 3x3 expression/pose grid versions into reusable child assets.
- [x] 4.10 Show sliced expression/pose child assets in the character portrait versions tab.

## Phase 4B: Character Bible and World Usage

- [x] 4B.1 Treat `Character` as a global reusable character body rather than a per-project duplicate.
- [x] 4B.2 Extend `CharacterStoryLink` with world usage fields: world, local identity, faction, costume, prompt tags, OOC and Off-Model notes.
- [x] 4B.3 Add character world usage API endpoints for list, create/update and remove.
- [x] 4B.4 Make creative project character sync reuse existing global characters by name and attach project/world usage records.
- [x] 4B.5 Add character drawer world-usage management UI.
- [x] 4B.6 Add full Character Bible editor sections: identity, motivation, speech, behavior boundaries, abilities and arc.
- [x] 4B.7 Use world usage overrides during storyboard/comic/image prompt generation.
- [x] 4B.8 Feed Character Bible fields into portrait prompt synthesis.
- [x] 4B.9 Redesign character detail drawer with a summary identity board and Bible quick panels.
- [x] 4.4 Add portrait version list with preset/model/time and set-main action.
- [ ] 4.5 Preserve existing quick generation behavior for users who only fill appearance/costume.
- [x] 4.8 Add AI-assisted Character Bible enrichment for legacy characters and generated draft characters.

## Phase 5: Creative Project Integration

- [x] 5.1 Make project storyboard/comic image prompt generation read character visual profiles.
- [x] 5.2 When supported by the selected backend, pass main portrait image as a reference image.
- [x] 5.3 Add manual per-panel reference override.
- [x] 5.4 Record character and portrait Asset Hub lineage on generated panel images.
- [x] 5.5 Remove the demo/test data fill entry from the creative project workbench UI.
- [x] 5.6 Store a per-generation reference image collection snapshot with source labels.
- [x] 5.7 Add AI reference-card matching for script scenes and storyboard panels.
- [x] 5.8 Show matched reference-card thumbnails across script, storyboard and comic pages.
- [x] 5.9 Add preflight reference coverage and image-backend capability hints before batch storyboard generation.
- [x] 5.10 Allow generated outputs to be promoted back into the project reference-card collection.
- [x] 5.11 Add ordered novel-body reader with chapter TOC, previous/next navigation and Markdown export.
- [x] 5.12 Add backend novel-body quality gate for short summaries/repeated output and local schema coercion for chapter-outline scene fields.
- [ ] 5.13 Add tests for prompt injection and lineage metadata.

## Verification

- [x] 6.1 Verify existing characters without visual profiles can still generate portraits.
- [x] 6.2 Verify `identity_board_16_9` prompt includes layout, no-overlap, face anchor, multi-view, expression and detail study rules.
- [x] 6.3 Verify each preset maps to the expected output intent: main portrait, multi-view sheet, identity board, expression pack, action pose pack and transparent/white-background material.
- [ ] 6.4 Verify generated portrait versions remain visible in Asset Hub and one can be selected as main.
- [x] 6.5 Verify a storyboard panel prompt includes linked character profile and portrait reference information.
- [x] 6.6 Run backend tests and frontend build for changed areas.
- [ ] 6.7 Verify a generated 3x3 portrait grid creates 9 child image assets with source-version lineage.
