---
name: ylcraft-creative-workflow
description: Drive YLCraft creative-project workflows through the local API. Use when Codex needs to create or continue novels, short-drama projects, character syncing, chapter outlines, prose bodies, scripts, comic pages, storyboards, reference matching, generation logs, or project export inside the YLCraft repo.
---

# YLCraft Creative Workflow

Use this skill when a request is about producing or continuing a YLCraft creative project: novel planning, character cards, chapter outlines, prose chapters, short-drama scripts, comic pages, storyboards, reference assets, or production logs.

## Default Approach

Prefer the YLCraft backend API over direct database writes. The API preserves generation logs, project content versions, asset links, and frontend-visible state.

Default local API base:

```text
http://127.0.0.1:8000/api/v1
```

Use `--base-url` when the backend runs elsewhere.

## Workflow Script

Use `scripts/creative_project_workflow.py` for repeatable operations:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py list-projects
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py inspect --project-id <id>
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py export-novel --project-id <id> --out exports/novel.md
```

Preferred text model for long prose, unless the user chooses another:

```text
provider=deepseek
model=deepseek-v4-pro
```

For batch operations, pass chapter ranges such as `1`, `1,3,5`, or `1-6`.

## Production Order

For a new or incomplete project, run stages in this order:

1. Create or inspect project.
2. Generate project outline.
3. Sync outline characters into the character library.
4. Generate chapter plan.
5. Generate chapter outlines.
6. Generate novel正文.
7. Generate short-drama scripts.
8. Generate storyboards from scripts.
9. Match reference assets before image generation.
10. Split comic pages from storyboards when comic output is needed.
11. Export novel or inspect logs for review.

Do not start expensive image generation until the story text, script, reference-card matching, and user intent are clear.

For the backend-orchestrated version, prefer:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py run-pipeline --project-id <id> --chapters 1-3 --stages chapter_outline novel_body script storyboard match_references
```

## References

Read `references/api-workflows.md` when you need endpoint details, content type names, or recommended command examples.
