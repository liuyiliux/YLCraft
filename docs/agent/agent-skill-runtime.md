# YLCraft Agent Skill Runtime Guide

This guide explains how YLCraft loads, routes, reviews and manages Agent Skills.

## Core Idea

YLCraft follows the useful parts of DeerFlow and Hermes without replacing the current Agent runtime:

- DeerFlow-style progressive skill loading: keep a compact skill index in context, then load full skill instructions only when routed or explicitly activated.
- Hermes-style procedural memory: successful workflows can become reviewable skill drafts instead of being forgotten after one run.
- YLCraft-specific safety: external skills and agent-generated skills must pass human review before becoming active.

Skills describe reusable procedures. They should not store project content, user secrets or one-off conversation data.

## Skill Package Format

A skill package is a directory containing `SKILL.md`.

Built-in skills live under:

```text
backend/app/skills/**/SKILL.md
```

Approved user skills live under:

```text
backend/app/skills/user/<skill-name>/SKILL.md
```

Minimum example:

```markdown
---
name: storyboard_generation
title: 分镜生成
description: 根据正文、脚本或章节细纲生成分镜列表，并关联角色、场景和参考图。
version: 1.0.0
skill_type: workflow
category: creative
tags: [storyboard, creative-project, image-prompt]
triggers:
  keywords: [分镜, 镜头, storyboard, 画面拆分]
  context_keys: [project_id, chapter_id, script_id]
  tools: [create_storyboard, list_project_characters]
requires_tools: [create_storyboard]
risk: write
---

# 分镜生成

## When To Use

用户希望把小说正文、短剧脚本或章节细纲拆成镜头画面时使用。

## Procedure

1. 先读取项目、章节、角色和已有素材上下文。
2. 保留用户已经确认的人物、场景和风格设定。
3. 输出可执行的镜头序列，而不是泛泛的创意建议。
4. 需要生成图片时，先匹配参考卡，再进入生图工具。

## Verification

确认每个分镜都有画面主体、动作、景别、参考卡或缺失说明。
```

## Metadata Rules

Required fields:

- `name`: stable id, used by slash activation and routing.
- `description`: compact capability summary.
- `skill_type`: usually `workflow`, `tooling` or `knowledge`.

Recommended fields:

- `title`: UI display name.
- `version`: package version.
- `category`: broad product area.
- `tags`: searchable labels.
- `triggers.keywords`: user message terms that should route to this skill.
- `triggers.context_keys`: context fields that make this skill relevant.
- `triggers.tools`: tools that imply this skill is useful.
- `requires_tools`: tools the skill needs to execute well.
- `risk`: `read`, `write`, `delete` or `costly`.

Keep trigger keywords specific. Generic words like "继续", "优化" or "处理" create noisy matches.

### Creative Narrative Contract

An Agent Skill may also declare an optional `creative` object when it is safe to contribute to a Creative Project Context Pack:

```yaml
creative:
  compatible_project_types: [novel]
  compatible_genres: ["*"]
  stages: [prose_draft]
  context_contribution: "A concise, bounded instruction for the model."
  input_schema: {chapter_contract: object, narrative_context: string}
  output_schema: {candidate_prose: string}
  prohibited_mutations: [approved_novel_body, locked_project_bible, confirmed_ledger]
  auto_apply: true
```

All fields except `auto_apply` are required when `creative` is present. The creative runtime uses only the compact `context_contribution`, never the entire Skill body. A project may explicitly select packages through `settings.creative_skill_ids`; automatic application additionally requires project type, genre and stage compatibility. The resolved IDs and checksums are stored in `ProjectNarrativeContextSnapshot`. A Skill is procedural guidance, not permission to promote prose, accept facts, activate foreshadowing, publish externally or spend generation credits.

## Routing

The runtime selects skills from four signals:

1. Profile defaults: skills attached to the current agent profile get priority.
2. Slash activation: leading `/skill_name` or `/bundle_name` explicitly activates skills.
3. Metadata triggers: keywords, context keys and allowed tools score matching skills.
4. Compatibility fallback: legacy routing stays available during migration.

The model context receives:

- Level 0: compact skill index, so the agent knows what exists.
- Selected skills: full `SKILL.md` body for matched or explicitly activated skills.
- Optional references/templates: loaded only when requested.

This avoids dumping every skill body into every conversation.

## Tool Registry Notes

Agent tools are internal APIs. When a tool category, name, input, output type or risk level changes, update tests and this guide.

### Supervisor Delegation Tool

`delegate_agent_tasks` 是内部 `agent_runtime` 工具，而不是领域 Skill。只有同时满足两个条件才会向模型暴露：Profile 设置 `can_delegate=true`，且工具授权包含该工具或 `*`。

- Input: `tasks` (1-6 items) and `join_strategy` (`all` or `best_effort`).
- Each task requires `task_key`, `profile_id`, and `objective`; optional `context` is bounded and `depends_on` references only task keys in the same call.
- Independent tasks run concurrently; dependencies run in topological batches.
- Output: durable delegation rows, linked child Run IDs, summary and `joined_observation`.
- The output is appended to the parent as a normal observation, so the parent planner resumes instead of ending at delegation.
- The module-level registry handler cannot execute directly because execution requires the current user, parent Run and DB session. `AgentService` injects that scoped runtime handler.

This is separate from Skills: Skills explain reusable procedure; the Supervisor tool creates real child Agent executions. A Worker with `allowed_tools=["*"]` still cannot access delegation unless `can_delegate` is explicitly enabled.

Canvas tool contract: `apply_creative_canvas_operations` accepts `connect_nodes` only when the connection supplies `fromNodeId`, `fromPortId`, `toNodeId`, and `toPortId`. Invalid connection operations are skipped rather than persisted.

Current image prompt reference tools:

- `list_image_prompt_sources`: `read`, lists configured prompt-library sources and sync status.
- `search_image_prompt_references`: `read`, searches synced prompt references by keyword, tag, category or source.
- `get_image_prompt_reference`: `read`, returns the full prompt reference detail.
- `refresh_image_prompt_sources`: `write`, refreshes one or all configured sources from remote repositories.
- `save_image_prompt_reference_as_asset`: `write`, explicitly saves one selected reference as an Asset Hub text asset. Synced references are not imported into Asset Hub automatically.

## Fanqie Tools

Fanqie tools use a configured `PlatformConnection` and never expose its cookie to the model.

- `list_fanqie_my_books`, `get_fanqie_book_stats`, and `get_fanqie_hot_list` are `read` tools that call the existing author-platform read APIs.
- `preview_fanqie_project_publish` is a local `read` preflight: it resolves the project binding, validates `novel_body`, target identifiers, and returns missing fields without contacting Fanqie.
- `get_fanqie_project_publish_status` is a local `read` tool over `ProjectPublishRecord`.
- `publish_fanqie_project_chapter` is a `write` tool. The Agent runtime must request confirmation before it runs. It writes only the specified `item_id`, never retries silently, and should be preceded by the preflight. Live validation must use a user-created isolated `[TEST]` chapter.

## Slash Activation

Users can force a skill:

```text
/storyboard_generation 把第三章拆成 12 个分镜
```

Multiple activations are allowed at the start of the message:

```text
/character_visual_card /portrait_prompt 给角色阿青补视觉卡并生成立绘提示词
```

If a skill is disabled or unknown, the runtime returns a diagnostic instead of silently guessing.

## Bundles

Bundles group multiple skills into one reusable workflow.

Built-in bundles live under:

```text
backend/app/skills/bundles/*.yaml
```

User bundles live under:

```text
backend/app/skills/user/bundles/*.yaml
```

Example:

```yaml
name: character_portrait_workflow
description: 角色设定、视觉卡、立绘提示词、参考图和生图闭环。
skills:
  - character_visual_card
  - portrait_prompt
  - reference_match
  - image_generation_workflow
instruction: |
  优先读取角色现有设定和素材库参考，不要重设已确认外貌。
  先补视觉卡，再预览提示词；用户确认后再进入成本型生图。
```

Activate it with:

```text
/character_portrait_workflow 给女主做一套稳定参考图方案
```

The management UI marks missing skills inside bundles so broken workflows are visible.

## Draft Review

External or agent-created skills do not become active immediately.

Supported draft sources:

- Pasted `SKILL.md`
- Raw `SKILL.md` URL
- GitHub blob URL
- GitHub repository URL
- Successful Agent run converted into a reusable workflow draft
- Route-rule edits from the skill management UI

Review flow:

1. Create a pending draft.
2. Inspect the content and route metadata diff.
3. Approve to write under `backend/app/skills/user/...`.
4. Reject to leave active skills unchanged.
5. Refill the editor from a rejected draft when another revision is needed.

Route-rule edits always create drafts. They do not overwrite active packages directly.

## Match Testing

Use the skill management panel's "匹配测试" to debug routing.

Inputs:

- User message
- Optional context JSON
- Optional allowed tool list
- Optional target skill

Outputs:

- Selected skills
- Scores and match reasons
- Activated bundles
- Diagnostics for a target skill that did not match

Match testing does not run tools and does not start a real Agent run.

## Runtime Observability

Agent runs record selected skill information in the run/context snapshot:

- selected skill ids
- route reasons
- activated bundle ids
- bundle instruction
- skill usage and success counters

The Agent page can show which skills were used by a run and link back to the skill management panel.

## Authoring Checklist

Before approving a skill:

- The `name` is stable and unique.
- The description says when to use it, not just what it is.
- Keywords are concrete and not overly broad.
- `requires_tools` names exist in the Agent tool registry.
- The procedure preserves existing project facts instead of overwriting them.
- Risk matches behavior: read-only lookup should not be marked costly or write.
- The verification section tells the agent how to know the workflow succeeded.

## Validation Commands

Backend:

```powershell
backend\venv_win\Scripts\python.exe -m pytest backend\tests\test_agent_center.py -q
```

OpenSpec:

`agent-skill-package-runtime` is complete and archived under `openspec/changes/archive/agent-skill-package-runtime/`. Use it for historical reference; active validation should focus on current changes unless the archived spec is restored.

Frontend:

```powershell
cd frontend
npm.cmd run build
```

The frontend build runs TypeScript in no-emit mode. Build caches and generated
Vite config artifacts are ignored, so a successful build must not add tracked
generated files to the worktree.
