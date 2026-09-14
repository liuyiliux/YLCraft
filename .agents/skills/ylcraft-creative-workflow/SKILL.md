---
name: ylcraft-creative-workflow
description: Drive YLCraft creative-project workflows through the local API. Use when Codex needs to create or continue novels, short-drama projects, character syncing, chapter outlines, prose bodies, scripts, comic pages, storyboards, reference matching, lightweight content packages (picture books, knowledge cards, platform posts), platform output adapters, generation logs, or project export inside the YLCraft repo.
---

# YLCraft Creative Workflow

Use this skill when a request is about producing or continuing a YLCraft creative project: novel planning, character cards, chapter outlines, prose chapters, short-drama scripts, comic pages, storyboards, reference assets, production profiles, lightweight content packages, or production logs. It is also the repo's reusable API-facing workflow for external agents; prefer stable HTTP IDs over direct database writes.

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

## Content Packages (Lightweight)

When the request is a picture book, knowledge cards, a platform post, or a single-shot experiment, do **not** force the staged narrative chain (outline → chapter plan → prose → storyboard). Use a **content package** instead: topic or source material → package plan → per-item text and image prompts → platform outputs. No outline, project bible, or prose is required.

A package is a versioned `ProjectContent` with `content_type=content_package`: a `package_type`, an ordered `items` list (one item per page/card/shot), and any platform `outputs` produced so far.

```bash
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-plan --project-id <id> --topic "十二生肖" --brief "一页一个生肖，儿童科普" --item-count 12
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-get --project-id <id>
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-outputs --project-id <id>
python .agents/skills/ylcraft-creative-workflow/scripts/creative_project_workflow.py package-item-retry --project-id <id> --item-id rat --brief "改写得更口语"
```

- Omit `--adapters` on `package-outputs` to produce whatever the project's profile declares; add `--no-save` to preview without appending a version.
- Adapters are **local format translation only**: they never publish, never call WeChat/Xiaohongshu/video platforms, and never rewrite the source `items`.
- Retrying one item leaves every other item untouched and marks only the outputs that reference it as `stale`.
- `short_video` and `pdf_ebook` are `planning_only`: they emit planning structure (shot table, page structure) that a later rendering step consumes, not finished media files. Do not report them as final deliverables.
- `article_package`, `social_carousel`, `shot_list` and `single_media` are currently **API-only** — callable from here but with no dedicated UI yet.
- **Plan stages differ by production family.** For a content-package project, propose package stages — `package_plan` → `item_text` → `item_prompt` → `media_batch` → `package_outputs` (optional `item_review`, `layout`). Do not propose `outline` / `chapter_plan` / `chapter_outline` for a picture book or card set: their orchestration unit is the **item**, not the chapter. Narrative projects keep the existing stages. The Agent Context Pack exposes `production_family`, `package_type` and `planning_unit` alongside the stage list so you can tell which family you are in.

Read `references/api-workflows.md` for package types, adapter types, per-profile defaults, validation tiers, and the full command list.

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
