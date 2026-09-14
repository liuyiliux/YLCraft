# YLCraft Creative Project API Workflows

## Base

Default API base URL:

```text
http://127.0.0.1:8000/api/v1
```

All responses usually use:

```json
{"success": true, "data": ...}
```

The workflow script unwraps `data` automatically for most commands.

## Core Endpoints

External-agent capability and asset loop:

- `GET /ai/capabilities?available_only=true`
- `POST /assets/upload` (multipart; image/video/audio/text/3D)
- `POST /images/generate`
- `POST /videos/generate`
- `POST /model-3d/generate`
- `GET /tasks/{task_id}`
- `GET /logs?scene=<image|video|model3d|llm>`
- `GET /assets/{asset_id}`

The capability response is authoritative for provider/model selection. Never put API keys in an external-agent prompt or persist them in project metadata.

Projects:

- `GET /creative-projects`
- `POST /creative-projects`
- `GET /creative-projects/{project_id}`
- `PATCH /creative-projects/{project_id}`
- `DELETE /creative-projects/{project_id}`
- `POST /creative-projects/{project_id}/fill-demo-data`
- `POST /creative-projects/{project_id}/sync-project-bible`

Project creation accepts `production_profile`: `vertical_drama`, `storybook`, `knowledge_content`, `platform_note`, `novel_serial`, or `single_shot`.

Generation:

- `POST /creative-projects/{project_id}/generate-outline`
- `POST /creative-projects/{project_id}/sync-characters`
- `POST /creative-projects/{project_id}/generate-chapter-plan`
- `POST /creative-projects/{project_id}/generate-chapter-outline`
- `POST /creative-projects/{project_id}/regenerate-chapter-outline-scenes`
- `POST /creative-projects/{project_id}/generate-novel-body`
- `POST /creative-projects/{project_id}/refine-novel-body`
- `POST /creative-projects/{project_id}/split-comic-pages`
- `POST /creative-projects/{project_id}/generate-script`
- `POST /creative-projects/{project_id}/generate-storyboard`
- `POST /creative-projects/{project_id}/match-reference-assets`
- `POST /creative-projects/{project_id}/run-pipeline`
- `POST /creative-projects/{project_id}/writer-room/step/{step}`
- `POST /creative-projects/{project_id}/writer-room/run`
- `POST /creative-projects/{project_id}/writer-room/promote`

Inspection:

- `GET /creative-projects/{project_id}/contents`
- `GET /creative-projects/{project_id}/production-plan`
- `GET /creative-projects/{project_id}/production-plan?include_history=true`
- `PUT /creative-projects/{project_id}/production-plan`
- `GET /creative-projects/{project_id}/assets`
- `GET /creative-projects/{project_id}/generation-logs`
- `GET /creative-projects/logs/generation`
- `GET /creative-projects/{project_id}/canvas`

## Content Package (lightweight)

A content package is the non-narrative counterpart of a production plan: a versioned `ProjectContent` record with `content_type=content_package`. It holds a `package_type`, a title/topic/brief, a `style`, an ordered `items` list (one item per page/card/shot), and any platform `outputs` produced so far. It does **not** require prose, an outline, or a project bible.

Endpoints:

- `POST /creative-projects/{project_id}/content-package/plan` — one-shot plan + convert (`topic`, `brief`, `item_count` 1-80, `prompt_only`, `provider`, `model`); returns the package but does not persist it
- `PUT /creative-projects/{project_id}/content-package` — save a versioned package (`package`, optional `source_content_id`)
- `POST /creative-projects/{project_id}/content-package/outputs` — translate the current package into platform formats (`adapters` list, `save` bool). **Leave `adapters` empty to use the profile's declared `output_adapters`.**
- `POST /creative-projects/{project_id}/content-package/items/{item_id}/retry` — regenerate a single item (`brief`, `prompt_only`, `provider`, `model`); other items are untouched and outputs referencing it become `stale`
- `GET /creative-projects/{project_id}/contents?content_type=content_package` — read package versions

Package types: `page_book`, `knowledge_cards`, `article_package`, `social_carousel`, `shot_list`, `single_media`. The last four are currently **API-only** (`ui_enabled=false`) — they work through the API but have no dedicated UI yet.

Adapter types (`adapter_type` in each output): `wechat_official_account`, `xiaohongshu_carousel`, `short_video`, `pdf_ebook`, `asset_bundle`. Adapters are named by **output shape, not platform** — short-video platforms share one structure. `GET`-able catalog: the `available_adapters` field in any `outputs` response.

Which adapters a profile produces by default:

| `production_profile` | declared `output_adapters` |
| --- | --- |
| `storybook` | `pdf_ebook`, `asset_bundle` |
| `knowledge_content` | `wechat_official_account`, `xiaohongshu_carousel`, `asset_bundle` |
| `platform_note` | `wechat_official_account`, `xiaohongshu_carousel`, `asset_bundle` |
| `single_shot` | `asset_bundle` |

Rules:

- Adapters are **local-only translation**: they never call WeChat/Xiaohongshu/video platforms, never publish, and never write back into the source package's `items`.
- Every output carries `source_package_id`, `source_package_version` and `source_item_ids`, so "the source changed and this output is outdated" is decidable. Editing an item marks only the outputs that reference it as `stale`; it does not invalidate the whole package.
- `short_video` and `pdf_ebook` are declared `planning_only`: they emit structure/planning data (shot table, page structure) that a later step renders. Do not present them as final media files.
- The backend does not resolve `asset_ids` into URLs (the frontend does). When no URL exists, `wechat_official_account` emits `<img data-asset-id="...">` placeholders instead of silently dropping images.
- Package validation has two tiers: structural problems (unknown type, non-array items, `status` outside its domain, item count above the cap) are hard errors; content-quality issues (below the recommended item count, missing recommended fields, no media prompt at all) are returned as `warnings` and still saveable.

Commands:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-get --project-id <id>
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-plan --project-id <id> --topic "十二生肖" --brief "一页一个生肖，儿童科普" --item-count 12
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-outputs --project-id <id> --adapters pdf_ebook,asset_bundle
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-outputs --project-id <id> --no-save
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-item-retry --project-id <id> --item-id rat --brief "改写得更口语"
```

`--no-save` previews outputs without appending a package version; the saved version is what the UI's "输出适配" check reads.

## Novel Source → World Project

Novel-source world extraction builds a world project from an imported novel. All extraction APIs preview first; `apply` is the only write into a project.

- `POST /novel-sources/import-txt` (multipart), `POST /novel-sources/import-bookshelf`
- `GET /novel-sources`, `GET /novel-sources/{snapshot_id}`
- `GET /novel-sources/domains` — detectable vs extractable world modules
- `POST /novel-sources/{snapshot_id}/plan` — per-module AI detection (costly)
- `POST /novel-sources/{snapshot_id}/extract` — extract candidates for chosen domains (`mode=delta` continues from the last checkpoint)
- `GET /world-extraction-runs/{run_id}/candidates`, `POST /world-extraction-runs/{run_id}/candidates/decide`
- `GET /world-extraction-runs/{run_id}/reconcile` — deterministic duplicate/alias/evidence-overlap/timeline hints (read-only)
- `POST /world-extraction-runs/{run_id}/apply` — the single write point (characters go to the character library, other domains become locked `world_asset` facts)
- `POST /novel-sources/{snapshot_id}/chunks/index` then `POST /novel-sources/{snapshot_id}/chunks/search` — optional vector index and hybrid retrieval
- `POST /novel-sources/{snapshot_id}/derive` — completed sources only; creates an adaptation/continuation/fan-work project and copies confirmed source facts as a read-only `fact_layer=source_canon` layer
- `POST /novel-sources/{snapshot_id}/sync` — serial sources only; append new chapters without rebuilding

Structured world maps are separate editable documents (not extraction candidates):

- `GET /world-maps?project_id=...` — list maps
- `POST /world-maps` — create a map (`title`, optional `project_id`/`snapshot_id`, `map_json` with `regions`/`nodes`/`routes`)
- `GET /world-maps/{map_id}`, `PUT /world-maps/{map_id}` (revision CAS), `DELETE /world-maps/{map_id}`

Rules: candidates are preview-only until decided and applied; `reconcile` never merges anything; never pass real user/remote novel text to external services outside these APIs.

## Content Types

Common project content types:

- `chapter_outline`
- `novel_body`
- `script`
- `comic_pages`
- `storyboard`
- `project_bible`
- `world_asset`
- `scene_beats`
- `character_rehearsal`
- `prose_draft`
- `prose_humanized`
- `prose_review`
- `prose_rewrite`
- `production_plan`
- `content_package`

Use `GET /creative-projects/{project_id}/contents?content_type=<type>` to fetch a stage.

## Director Production Plan

The production plan is a versioned `ProjectContent` record with `content_type=production_plan`. It holds only user-visible planning data: a production profile, editable nodes, dependency IDs, input/output Asset Hub or project-content IDs, canvas document IDs, concise planning summaries, provider/model selections, node status, and confirmation points. It must not carry hidden chain-of-thought.

Read the active revision:

```text
GET /creative-projects/{project_id}/production-plan
```

Read all revisions:

```text
GET /creative-projects/{project_id}/production-plan?include_history=true
```

Save a new revision. `base_plan_id` is optional; when present it becomes the revision provenance link.

```json
PUT /creative-projects/{project_id}/production-plan
{
  "base_plan_id": "previous-plan-content-id",
  "plan": {
    "title": "四页恐怖漫画",
    "goal": "完成四页可生成的恐怖漫画制作计划",
    "production_profile": "storybook",
    "status": "draft",
    "confirmation_status": "pending",
    "asset_ids": ["character-reference-asset-id"],
    "nodes": [
      {
        "id": "story",
        "stage": "story_seed",
        "label": "故事与页节拍",
        "specialist_role": "story-designer",
        "planning_summary": {"intent": "建立会移动的肖像画"},
        "requires_confirmation": true
      },
      {
        "id": "visual",
        "stage": "image",
        "label": "第三页构图",
        "specialist_role": "visual-director",
        "depends_on": ["story"],
        "input_asset_ids": ["character-reference-asset-id"],
        "rerun_scope": "downstream",
        "requires_confirmation": true
      }
    ]
  }
}
```

Saving a plan is not a paid generation, but the plan's confirmation points still govern any later costly, download, publishing, or destructive operation.

### Plan stages by production family

Each node's `stage` is a free-form string (unknown values are not rejected), but the two families have different orchestration units, so they use different stage vocabularies. `GET`-able via the Agent Context Pack's `project.production_profile` block, which also reports `production_family`, `package_type` and `planning_unit`.

| Family | Stages |
| --- | --- |
| `content_package` | `package_plan` (topic → package skeleton) → `item_text` (per-item body) → `item_prompt` (per-item image/video prompt) → `media_batch` (costly image/video tasks, one confirmation) → `package_outputs` (adapter outputs); optional `item_review`, `layout` |
| `narrative` | `outline` → `chapter_plan` → `chapter_outline` → `script` / `novel_body` → `storyboard` → `video` / `comic_pages` |

Do not propose narrative stages for a content-package project: its unit of work is the **item** (page / card / shot / article package), and proposing `chapter_outline` for a picture book leads to a plan nobody can execute. Per profile: `storybook` and `knowledge_content` use the full package chain; `platform_note` (`planning_unit=package`) is `package_plan` → `item_text` → `package_outputs` with media stages optional; `single_shot` is `package_plan` → `item_prompt` → `media_batch`.

## Recommended Long-Prose Defaults

For novel body generation and rewrite:

```json
{"provider": "deepseek", "model": "deepseek-v4-pro"}
```

Keep chapter body quality around 3000-5000 Chinese characters unless the user asks for another length.

## Useful Commands

Inspect a project:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py inspect --project-id <id>
```

Generate chapter outlines for a range:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py generate-chapter-outline --project-id <id> --chapters 1-12 --provider deepseek --model deepseek-v4-pro
```

Sync editable Project Bible and world asset cards from the latest outline:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py sync-project-bible --project-id <id>
```

Generate novel bodies for a range:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py generate-novel-body --project-id <id> --chapters 1-12 --provider deepseek --model deepseek-v4-pro
```

Generate scripts:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py generate-script --project-id <id> --chapters 1-12 --provider deepseek --model deepseek-v4-pro
```

Generate storyboard from existing scripts:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py generate-storyboard --project-id <id> --chapters 1-12 --provider deepseek --model deepseek-v4-pro
```

Run the backend orchestrated pipeline:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py run-pipeline --project-id <id> --chapters 1-12 --stages chapter_outline novel_body script storyboard match_references --provider deepseek --model deepseek-v4-pro
```

Run the recommended writer-room flow for one chapter:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-run --project-id <id> --chapter 2 --provider deepseek --model deepseek-v4-pro --continue-on-error
```

Run the writer-room flow with the user's currently requested text backend:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-run --project-id <id> --chapter 2 --provider "<connector-name>" --model "<model-name>" --steps scene_beats character_rehearsal prose_draft prose_humanized prose_review --continue-on-error
```

For long Chinese prose, prefer `deepseek-v4-pro` when the user says "用 deepseekv4 那个写" or asks for more natural novel writing:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-run --project-id <id> --chapter 2 --provider deepseek --model deepseek-v4-pro --steps scene_beats character_rehearsal prose_draft prose_humanized prose_review --continue-on-error
```

Run a single writer-room pass:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter 2 --step prose_review --provider deepseek --model deepseek-v4-pro
```

Review and rewrite without rerunning the whole flow:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter 2 --step prose_review --provider deepseek --model deepseek-v4-pro
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter 2 --step prose_rewrite --instruction "按主编意见重写，保留剧情事实，压低解释感，增加动作、物件互动和潜台词" --provider deepseek --model deepseek-v4-pro
```

Run a selected-paragraph rewrite:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter 2 --step prose_rewrite --selected-text "需要重写的原文片段" --instruction "少解释，多动作和潜台词" --provider deepseek --model deepseek-v4-pro
```

Promote a writer-room draft or rewrite to latest readable prose:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-promote --project-id <id> --content-id <writer-room-content-id>
```

Only promote after reviewing the candidate content. Promotion creates a new `novel_body` version; previous readable prose remains in version history.

Export the ordered novel:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py export-novel --project-id <id> --out exports/novel.md
```

## Guardrails

- Prefer API calls over direct database edits.
- Inspect generation logs after failures before retrying expensive operations.
- Do not overwrite locked content unless the user explicitly asks.
- Match reference assets before image generation so character/style consistency can improve.
- Keep generated prompts and raw responses visible through project generation logs.
