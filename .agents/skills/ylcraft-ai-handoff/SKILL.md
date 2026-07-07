---
name: ylcraft-ai-handoff
description: Take over, continue, audit, or hand off YLCraft development across multiple AI agents and machines. Use when the user asks to continue work, summarize progress, clean docs, inspect project state, prepare a handoff, update architecture/spec records, or onboard another AI without rediscovering the whole repository.
---

# YLCraft AI Handoff

## Overview

Use this skill to rebuild project context from repository facts, protect other agents' dirty work, update the correct documentation, and leave a concise handoff for the next AI.

## Start Workflow

1. Run `git status --short --branch` and `git log --oneline -8`.
2. Read `AGENTS.md`, `docs/README.md`, and `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`.
3. Read `docs/architecture/API_SURFACE.md` when the task touches backend APIs.
4. Read `docs/AI_HANDOFF_PROTOCOL.md` for collaboration rules.
5. Inspect active OpenSpec tasks under `openspec/changes/*/tasks.md`.
6. Locate the task's code and tests with `rg`, not by guessing from chat history.

## During Work

- Treat existing dirty files as user or another AI work. Do not revert unrelated changes.
- Keep implementation and architecture/API documentation in sync when changing APIs, database fields, Agent tools, Skill routing, or UI workflows.
- Treat Agent tools and Skills as internal APIs. If names, inputs, outputs, risk levels, authorization, or matching behavior change, update schema docs and tests in the same turn.
- For HTTP API changes, update `docs/architecture/API_SURFACE.md` and `docs/architecture/api_surface.json`; then judge whether `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` or a domain doc also needs a semantic update.
- Update OpenSpec task checkboxes as work completes.
- Prefer current code and tests over stale devlogs when facts conflict.
- If the user asks about design quality, use the installed frontend design skills explicitly and verify structure, spacing, density, and empty states.

## Handoff Workflow

Before stopping after meaningful work, update the durable docs first:

- `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` for module boundaries, data model, workflow, or status changes
- `docs/architecture/API_SURFACE.md` for API changes
- relevant `docs/agent/`, `docs/guides/`, or `docs/platform/` files for domain behavior

Documentation cleanup policy:

- Keep only current facts in `docs/README.md`, `docs/DESIGN.md`, `docs/architecture/`, and domain docs.
- Delete obsolete duplicate docs when their content is superseded by current fact sources.
- Archive completed OpenSpec changes under `openspec/changes/archive/`.
- Store external reference material under `docs/reference/`; it is not implementation truth.
- Keep `docs/devlog/` sparse. Use it only for cross-machine or long-running handoff, not routine progress.

Create or update `docs/devlog/YYYY-MM-DD_topic.md` only for long-running handoff or cross-machine context with:

- project goal
- changed files
- current progress
- validation results
- pending tasks
- key decisions
- error details
- next recommended step

Keep the handoff concise. Do not paste full logs unless the exact error text is important.

## Validation

Use the validation matrix in `docs/AI_HANDOFF_PROTOCOL.md`. At minimum, run `git diff --check` for docs-only changes.

## Important Project Facts

- `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` is the main system map.
- `docs/architecture/API_SURFACE.md` is the backend API map.
- Agent Skill Runtime is complete and archived under `openspec/changes/archive/agent-skill-package-runtime/tasks.md`.
- Creative project closed loop still has pending work.
- `docs/reference/` stores external materials and is not implementation truth.
- The project usually uses Git across two machines; avoid broad cleanup unless explicitly requested.
