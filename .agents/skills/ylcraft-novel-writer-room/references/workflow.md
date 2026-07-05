# Writer Room Workflow Reference

## Content Types

- `scene_beats`
- `character_rehearsal`
- `prose_draft`
- `prose_humanized`
- `prose_review`
- `prose_rewrite`
- `novel_body`

## API Endpoints

- `POST /api/v1/creative-projects/{id}/writer-room/step/{step}`
- `POST /api/v1/creative-projects/{id}/writer-room/run`
- `POST /api/v1/creative-projects/{id}/writer-room/promote`
- `GET /api/v1/creative-projects/{id}/contents`
- `GET /api/v1/creative-projects/{id}/generation-logs`

## Common Commands

Inspect:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py inspect --project-id <id>
```

Run selected steps:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-run --project-id <id> --chapter <n> --steps scene_beats character_rehearsal prose_draft prose_humanized prose_review --provider deepseek --model deepseek-v4-pro --continue-on-error
```

Review only:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter <n> --step prose_review --provider deepseek --model deepseek-v4-pro
```

Rewrite selected text:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter <n> --step prose_rewrite --selected-text "<原文片段>" --instruction "少解释，多动作和潜台词" --provider deepseek --model deepseek-v4-pro
```

Promote approved candidate:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-promote --project-id <id> --content-id <writer-room-content-id>
```

Export novel:

```powershell
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py export-novel --project-id <id> --out exports/novel.md
```

## Review Checklist

Before promoting, check:

- Does the chapter preserve canon and chapter outline facts?
- Does the prose avoid direct emotion labels when action can show it?
- Are dialogue, physical action, object interaction, and subtext present?
- Does the ending hook push the next chapter?
- Did generation logs capture prompt, request, raw response, normalized output, provider, and model?
