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

Projects:

- `GET /creative-projects`
- `POST /creative-projects`
- `GET /creative-projects/{project_id}`
- `PATCH /creative-projects/{project_id}`
- `DELETE /creative-projects/{project_id}`
- `POST /creative-projects/{project_id}/fill-demo-data`

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

Inspection:

- `GET /creative-projects/{project_id}/contents`
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

Use `GET /creative-projects/{project_id}/contents?content_type=<type>` to fetch a stage.

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
