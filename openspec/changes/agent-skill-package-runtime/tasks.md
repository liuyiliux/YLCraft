# Tasks

## M0. Specification And Migration Map

- [x] M0.1 Compare DeerFlow and Hermes skill/runtime ideas against current YLCraft Agent implementation.
- [x] M0.2 Define YLCraft-specific target architecture for file-backed skill packages.
- [x] M0.3 Inventory all current `BUILTIN_SKILL_TEMPLATES` and map each to a future `SKILL.md` package path.

## M1. Skill Package Loader

- [x] M1.1 Add `backend/app/services/agent/skill_loader.py`.
- [x] M1.2 Parse YAML frontmatter and Markdown body from `backend/app/skills/**/SKILL.md`.
- [x] M1.3 Validate required metadata: `name`, `description`, `skill_type`.
- [x] M1.4 Compute checksums and expose lightweight skill index records.
- [x] M1.5 Sync file-backed built-ins into `AgentSkill` while preserving usage/success counters.
- [x] M1.6 Keep `skill_templates.py` fallback during migration.

## M2. Built-In Skill Migration

- [x] M2.1 Create `backend/app/skills/creative/creative-project-advance/SKILL.md`.
- [x] M2.2 Create novel writing/review/humanize skill packages.
- [x] M2.3 Create character visual card and portrait prompt skill packages.
- [x] M2.4 Create storyboard, reference matching and comic image prompt skill packages.
- [x] M2.5 Create asset, platform, download, image/video generation, subtitle, BGM, clip, TTS, ebook and export quality skill packages.
- [x] M2.6 Remove migrated items from hardcoded fallback only after all built-ins migrate.

## M3. Metadata-Driven Routing

- [x] M3.1 Extend `SkillRoute` to include source, trigger type and matched terms.
- [x] M3.2 Load route triggers from skill metadata.
- [x] M3.3 Preserve profile default skill priority.
- [x] M3.4 Preserve hardcoded route fallback until all built-ins migrate.
- [x] M3.5 Add route preview service for UI/debugging.

## M4. Progressive Skill Loading

- [x] M4.1 Update `MemoryManager.build_memory_context()` to inject Level 0 skill index separately from full selected skill content.
- [x] M4.2 Load full skill body only for profile defaults, explicit activation or high-confidence routed skills.
- [x] M4.3 Add optional reference/template loading API for selected skill package files.
- [x] M4.4 Record selected skills in `AgentMemorySnapshot.snapshot_json`.

## M5. Slash Activation And Bundles

- [x] M5.1 Parse leading `/skill_name` tokens in agent user messages.
- [x] M5.2 Reject disabled or unknown skills with actionable feedback.
- [x] M5.3 Add bundle YAML support for recurring workflows.
- [x] M5.4 Expand bundles into activated skills and bundle instruction.
- [x] M5.5 Add regression tests for slash parsing precedence.

## M6. Agent-Managed Skill Drafts

- [x] M6.1 Detect skill-candidate runs from successful complex tool chains.
- [x] M6.2 Generate draft `SKILL.md` from run steps, failures, successful sequence and verification evidence.
- [x] M6.3 Add pending skill write storage with approve/reject status.
- [x] M6.4 Add API to list, diff, approve and reject skill drafts.
- [x] M6.5 On approval, write to user skill root and sync DB.

## M7. Skill Management UI

- [x] M7.1 Add Agent/Settings skill management page or drawer.
- [x] M7.2 Show skill index, source, enabled state, version, tags, triggers and usage metrics.
- [x] M7.3 Show full `SKILL.md` and package references.
- [x] M7.4 Add route preview: input message + context + allowed tools -> selected skills and reasons.
- [x] M7.5 Add pending draft review and diff approval UI.
- [x] M7.6 Add route-rule editing UI that generates a pending `SKILL.md` draft instead of overwriting active packages.
- [x] M7.7 Add target-skill route diagnostics that explain missing keywords, context keys and allowed tools.
- [x] M7.8 Highlight route-rule diffs in draft review and allow rejected drafts to refill the editor.

## M8. Validation

- [x] M8.1 Unit tests for loader parsing, validation, checksum and DB sync.
- [x] M8.2 Router tests for keyword/context/tool/profile/slash/bundle matches.
- [x] M8.3 Memory context tests proving full skill content is not injected unnecessarily.
- [x] M8.4 API tests for skill list/detail/route-preview/pending approval.
- [x] M8.5 Frontend build and smoke test after UI changes.
