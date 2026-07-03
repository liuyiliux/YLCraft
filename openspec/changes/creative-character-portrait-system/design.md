# Design: Creative Character Portrait System

## Current State

YLCraft already has:

- `characters` table with `appearance`, `costume_hint`, `personality`, `background`, `age_range`, `portrait_url`, `portrait_node_id` and freeze behavior.
- `/api/v1/characters/{id}/portrait/generate` that calls `AIService.generate_image` and writes a new Asset Hub character portrait version.
- Frontend prompt draft, copy and AI prompt optimization on the character page.
- Asset Hub facade support for `create_or_update_character_portrait`.

The missing piece is a stable design contract for what a portrait is supposed to be and how it flows into creative project image generation.

## Target Model

### Character visual card

Start with a JSON field or metadata extension instead of a large relational split. A future migration can promote these fields into first-class columns.

Recommended shape:

```json
{
  "identity_brief": "",
  "visual_tags": [],
  "face": "",
  "hair": "",
  "eyes": "",
  "skin": "",
  "temperament": "",
  "body_shape": "",
  "body_proportion": "",
  "costume": "",
  "costume_colors": [],
  "materials": [],
  "shoes": "",
  "accessories": [],
  "signature_items": [],
  "expression_set": ["neutral", "happy", "angry", "sad"],
  "pose_set": ["front", "side", "back", "sitting", "action"],
  "style": "",
  "background_rule": "plain_white_or_soft_off_white",
  "negative_constraints": []
}
```

This can initially live in `Character.metadata_json` if added, or in a dedicated `visual_profile_json` column. If no migration is desired for the first slice, the backend may synthesize it from existing character fields and store the expanded snapshot in Asset Hub metadata.

### Portrait presets

#### `main_portrait`

Single-character portrait or full-body illustration used by the character list and detail view.

Required traits:

- One character only.
- Clear face identity.
- Consistent costume and signature items.
- Simple background.
- Useful thumbnail.

#### `multi_view_sheet`

Standardized reference sheet focused on identity consistency.

Required traits:

- Front, side and back full-body views.
- Neutral pose for structural comparison.
- Same face, hair, outfit, body proportion and accessories across all views.
- Clean separation between views.
- No cropped face or hidden limbs.

#### `identity_board_16_9`

This preset implements the reference prompt from `短剧项目参考/立绘提示词.txt`.

Target output:

- 16:9 artistic character identity board.
- Same character as the only subject.
- Pure white or soft off-white background.
- No environment, props unrelated to the character, logos or watermarks.
- Left 1/4 area:
  - character ID block with positioning, short intro and visual tags.
  - large front-facing head portrait near the bottom as the face recognition anchor.
- Right 3/4 area:
  - top two-thirds: front, side and back full-body views.
  - top two-thirds action study: sitting, crouching, high-angle and low-angle poses.
  - lower area: three front-facing expression heads.
  - lower detail study: three to five key details, such as hair texture, collar, pendant, scar, weapon or accessory.
- Layout constraints:
  - no overlapping character images.
  - no cropped faces.
  - no hidden limbs.
  - no stacked figures.
  - no merged poses.
  - each view must have separation and breathing room.
  - do not use blueprint grids, catalog layout or repeated transition panels.

This preset is intended to become the default consistency reference for manga/storyboard generation.

#### `expression_pack`

Focused expression sheet for one character.

Required traits:

- Multiple front-facing head portraits.
- Expressions come from the character visual profile, defaulting to neutral, happy, angry, sad and shocked.
- Face structure, hair, eye shape, skin features and accessory identity remain stable.
- No outfit or hairstyle changes between expressions.

#### `action_pose_pack`

Focused body-language and action pose sheet for one character.

Required traits:

- Multiple pose studies such as combat stance, sitting, turning back, running, crouching, high-angle and low-angle.
- Same character identity, same outfit, same body proportion and same signature items.
- Poses are separated clearly and do not overlap.

#### `transparent_or_white_background`

Output option for downstream Live2D, compositing or material reuse.

Required traits:

- Single character only.
- Plain white, soft off-white or transparent background depending on backend capability.
- No environment, scene props, logos or watermarks.
- Full body should be preferred when the downstream use is Live2D or compositing.

#### `expression_pose_sheet`

Compact sheet focused on face and body variation while preserving the same visual identity.

Required traits:

- Same outfit and body proportion across all samples.
- Explicit expression list.
- Explicit pose list.
- Negative constraints prevent face drift, clothing drift and extra accessories.

This preset remains as a convenience alias for workflows that want expressions and poses in one compact sheet. New UI should prefer the clearer `expression_pack` and `action_pose_pack` presets.

#### `expression_grid_3x3` and `pose_grid_3x3`

Cutting-friendly sheets for producing reusable downstream assets.

Target output:

- One character only.
- Exactly 3 rows and 3 columns.
- Equal-sized cells with clear separation.
- Same face, outfit, body proportion and signature items in every cell.
- Expression grid cells should map to neutral, smile, laugh, shocked, angry, sad, shy, thinking and determined.
- Pose grid cells should map to front standing, side standing, back/turning, arms crossed, walking, running, sitting, ready stance and action close-up.

After generation, the user can run the grid slicing action. The backend crops the local image into 9 child `image` Asset Hub nodes under the character portrait node and records source node/version/representation lineage on each child.

## Prompt Builder

The prompt builder should be backend-owned so logs and generated assets can be reproduced.

Endpoint sketch:

```text
POST /api/v1/characters/{id}/portrait/prompt-preview
```

Request:

```json
{
  "preset": "identity_board_16_9",
  "visual_profile": {},
  "style_override": "",
  "negative_override": "",
  "language": "zh"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "preset": "identity_board_16_9",
    "prompt": "",
    "negative_prompt": "",
    "visual_profile_snapshot": {}
  }
}
```

Generation endpoint should accept the same `preset` and optional visual profile overrides:

```text
POST /api/v1/characters/{id}/portrait/generate
```

Additional request fields:

- `preset`
- `visual_profile`
- `style_override`
- `negative_override`
- `set_as_main`

## Asset Hub Storage

Each generated image creates or appends an Asset Hub version under the character portrait node.

Node metadata should include stable identity:

- `source = character_portrait`
- `character_id`
- `character_name`
- `main_portrait_version_id` when selected
- `visual_profile_current` if the latest card is saved

Version params should include:

- `preset`
- `provider`
- `model`
- `size`
- `seed`
- `negative_prompt`
- `visual_profile_snapshot`
- `prompt_template_version`

Representation extra should include:

- `url`
- `local_path`
- `is_main`
- `preset`

Grid-sliced child nodes should use:

- Node `asset_type = image`
- Node `parent_id = character.portrait_node_id`
- Node metadata:
  - `source = character_portrait_grid_slice`
  - `character_id`
  - `source_portrait_node_id`
  - `source_version_id`
  - `source_representation_id`
  - `grid_type`
  - `grid_index`
  - `row`
  - `col`
  - `label`
- Child version lineage mirroring the same source fields.
- A `derived_from` AssetRelation from the portrait node to each sliced image node.

## Main Portrait Selection

The system should allow selecting an existing Asset Hub portrait version as the character main portrait.

Endpoint sketch:

```text
POST /api/v1/characters/{id}/portrait/main
```

Request:

```json
{
  "node_id": "",
  "version_id": "",
  "representation_id": ""
}
```

Effects:

- Update `Character.portrait_url`.
- Update `Character.portrait_node_id`.
- Mark main version metadata on the Asset Hub node.
- Preserve all older versions.

## Frontend Workflow

Character drawer/form should add a "视觉卡 / 立绘" area:

- Visual card structured fields.
- Preset segmented control:
  - 主立绘
  - 多视图设定板
  - 16:9 身份板
  - 表情包
  - 动作姿态
  - 透明底/白底
- Prompt preview text area.
- Buttons:
  - Generate prompt.
  - Optimize prompt.
  - Copy prompt.
  - Generate portrait.
  - Set as main portrait.
  - Freeze appearance.
- Version list showing generated portraits with preset, model, time and "set main" action.

The page should avoid making users edit a giant prompt first. Structured fields should be the source of truth, and full prompt preview should be transparent and copyable.

## Storyboard Integration

Storyboard and comic image generation should read:

- project character links.
- selected `Character.portrait_node_id`.
- visual profile summary.
- main portrait representation path/url.

When the image backend supports reference images, the main portrait representation should be supplied as a reference image. When it does not, the character visual card summary must still be injected into the prompt.

Each generated panel image should record lineage:

- `project_id`
- `content_id`
- `panel_id`
- `character_ids`
- `portrait_node_ids`
- `portrait_version_ids`
- `prompt`

## Migration and Compatibility

- Existing characters without visual card data remain valid.
- Existing `appearance` and `costume_hint` are used to synthesize a default visual profile.
- Existing `portrait_url` can still be upgraded through the current upgrade endpoint.
- No existing generated portrait should be deleted.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Prompt too complex for some providers | Bad layout or text artifacts | Preset-specific negative constraints, model-specific templates later |
| Character fields become too many | UI friction | Use progressive disclosure and generated defaults |
| Reference-image support varies by provider | Inconsistent panel results | Fallback to prompt injection and record provider capability |
| Identity board includes text artifacts | Poor reference board | Explicitly allow minimal labels only and avoid dense text |
