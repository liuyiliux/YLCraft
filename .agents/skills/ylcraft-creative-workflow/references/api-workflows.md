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
