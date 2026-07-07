# YLCraft AI Entry Rules

This repository is developed by multiple AI agents across multiple machines. Before changing code, every agent must rebuild project context from source files instead of relying on chat history.

## Required First Reads

1. Read `docs/README.md` for the current documentation map.
2. Read `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` for the current system architecture and module boundaries.
3. Read `docs/architecture/API_SURFACE.md` when changing or calling backend APIs.
4. Read `docs/AI_HANDOFF_PROTOCOL.md` for the takeover and handoff workflow.
5. Check active OpenSpec tasks under `openspec/changes/*/tasks.md`.
6. Run `git status --short --branch` and treat existing changes as user or another agent's work.

## Work Rules

- Do not revert or overwrite unrelated dirty files.
- Prefer small, verifiable changes with focused tests.
- When changing APIs, database schema, agent tools, or UI workflows, update the architecture/API docs or OpenSpec tasks in the same turn.
- API work is not done until `docs/architecture/API_SURFACE.md` and `docs/architecture/api_surface.json` match the routes, and any semantic/module impact is reflected in `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` or the owning domain doc.
- Agent tools and Skills are treated as internal APIs: update their schema/spec docs and tests when inputs, outputs, risk level, or routing behavior changes.
- Use `docs/devlog/` for historical handoff notes only; it is not the default source of truth.
- For YLCraft-specific takeover or handoff work, use the `.agents/skills/ylcraft-ai-handoff` skill.
