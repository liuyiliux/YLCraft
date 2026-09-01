---
name: ylcraft-creative-workflow
description: Drive YLCraft creative-project workflows through the local API. Use when Codex needs to create or continue novels, short-drama projects, character syncing, chapter outlines, prose bodies, scripts, comic pages, storyboards, reference matching, generation logs, or project export inside the YLCraft repo.
---

# YLCraft Creative Workflow

Use this skill when a request is about producing or continuing a YLCraft creative project: novel planning, character cards, chapter outlines, prose chapters, short-drama scripts, comic pages, storyboards, reference assets, production profiles, or production logs. It is also the repo's reusable API-facing workflow for external agents; prefer stable HTTP IDs over direct database writes.

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
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py plan-get --project-id <id>
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py export-novel --project-id <id> --out exports/novel.md
```

Preferred text model for long prose, unless the user chooses another:

```text
provider=deepseek
model=deepseek-v4-pro
```

For batch operations, pass chapter ranges such as `1`, `1,3,5`, or `1-6`.

## Production Profiles

When creating a project, choose a `production_profile` instead of assuming every project needs prose:

- `vertical_drama`: outline → chapter plan → chapter outline → script → storyboard → video
- `storybook`: outline → page/chapter plan → script → storyboard → comic pages; prose is optional
- `knowledge_content`: topic/facts → script → storyboard → image/layout
- `platform_note`: content → multi-platform image generation → image editor/layout
- `novel_serial`: outline → chapter plan → chapter outline → novel body → review
- `single_shot`: idea or source asset → image/video experiment

The profile is stored in project settings and does not disable independent image, video, 3D, upload, or image-editor APIs.

## Director Plans

Before an Agent or an external workflow starts a multi-stage production run, read or create the project's versioned production plan. It is an editable, business-visible dependency graph: stages, specialist role, input/output content and Asset Hub IDs, canvas links, planning summaries, provider/model choices, and confirmation points. It is not hidden reasoning.

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py plan-get --project-id <id>
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py plan-save --project-id <id> --plan-file plans/horror-comic.json
```

Saving a plan creates a new `production_plan` content version. It is a `write` operation but is not itself a paid generation. Do not submit image, video, 3D, download, or publishing actions until the user has confirmed the relevant plan node; retain the previous plan ID as `--base-plan-id` when revising a known version.

## Production Order

For a new or incomplete project, run stages in this order:

1. Create or inspect project.
2. Generate project outline.
3. Sync outline characters into the character library.
4. Generate chapter plan.
5. Generate chapter outlines.
6. Generate novel正文 only for `novel_serial` or when explicitly requested.
7. Generate short-drama scripts when the selected profile requires them.
8. Generate storyboards from scripts.
9. Match reference assets before image generation.
10. Split comic pages from storyboards when comic output is needed.
11. Export novel or inspect logs for review.

When prose quality is the focus, use the writer-room flow before promoting a chapter:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-run --project-id <id> --chapter 1 --provider deepseek --model deepseek-v4-pro --continue-on-error
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-step --project-id <id> --chapter 1 --step prose_rewrite --instruction "压低解释，增加动作和潜台词"
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py writer-room-promote --project-id <id> --content-id <prose_rewrite-content-id>
```

Do not start expensive image generation until the story text, script, reference-card matching, and user intent are clear.

For an external-agent handoff, first call `GET /api/v1/ai/capabilities?available_only=true`, upload references with `POST /api/v1/assets/upload`, then call the image/video/3D generation API and poll the task endpoint. Preserve `project_id`, `content_id`, `production_profile`, `source_type`, `source_index`, and `source_title` whenever available.

For the backend-orchestrated version, prefer:

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py run-pipeline --project-id <id> --chapters 1-3 --stages chapter_outline novel_body script storyboard match_references
```

## References

Read `references/api-workflows.md` when you need endpoint details, content type names, or recommended command examples. It also covers the novel-source world-extraction loop (import → per-domain detection → evidence-validated extraction → reconcile → apply) and completed-source derivation into adaptation/continuation/fan-work projects.
