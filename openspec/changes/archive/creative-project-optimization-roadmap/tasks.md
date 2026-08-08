# Tasks

## Phase 1: Reference Cards and Character Portraits

- [x] 1. Define character card schema with text fields, visual fields, signature items, expressions, poses and negative constraints.
- [x] 2. Add character portrait prompt template that outputs full copyable prompts for multi-view reference sheets.
- [x] 3. Link generated character portraits back to project characters and asset hub nodes.
- [x] 4. Add reference-card grouping for character, background, style, world and panel-specific references.
- [x] 5. Let storyboard and comic image generation select project references automatically and allow manual override per panel.
- [x] 5.1 Add in-project character portrait generation from outline characters, using the project default image backend.
- [x] 5.2 Add non-destructive demo data fill for project outline, chapter plan, prose, scripts, storyboards and comic pages.
- [x] 5.3 Add project deletion that removes project-local content/log/link records while preserving asset library and character library data.

## Phase 2: World Bible Assets

- [x] 6. Split project outline into editable Project Bible sections.
- [x] 7. Add world asset roles: map, rule, faction, location, event, power-system, economy and style.
- [x] 8. Let chapter outline generation read locked world assets and continuity notes.
- [x] 9. Extract new world facts and continuity deltas from generated prose.
- [x] 10. Show world assets in the project workspace and asset hub.

## Phase 3: Storyboard Prompt V2

- [x] 11. Extend storyboard schema with panel goal, shot size, camera angle, camera motion, composition and blocking.
- [x] 12. Add scene card fields for location, time, weather, props, spatial axis, character positions and movement path.
- [x] 13. Generate detailed image prompts from role cards, scene cards, camera cards and style cards.
- [x] 14. Add full prompt preview/copy for each storyboard panel and comic page.
- [x] 15. Add actions to rewrite only the image prompt without changing source story/script.
- [x] 16. Add single-panel regeneration and batch panel generation with skip-existing behavior.

## Phase 4: Batch Production Queue

- [x] 16.1 Add a repo-local Codex skill and API workflow CLI for creative-project inspection, generation batches, reference matching and novel export.
- [x] 16.2 Add a backend non-destructive run-pipeline API for chapter-range production with skip-existing and continue-on-error controls.
- [x] 17. Add production queue UI for chapter ranges and selected stages.
- [x] 17.1 Show run summaries and per-step generated/skipped/failed results in the project workspace.
- [x] 18. Support skip existing, overwrite, retry failed and continue from failure.
- [x] 18.1 Expose skip-existing and continue-on-error controls in the batch production UI.
- [x] 18.2 Add non-destructive overwrite reruns as new latest versions and retry-failed action from the latest run result.
- [x] 19. Persist queue step logs with provider, model, prompt template, duration and error.
- [x] 20. Add manual review checkpoints before expensive image generation.
- [x] 20.1 Add storyboard reference preflight summary and warnings before batch image generation.

## Phase 5: Multi-Agent Exploration

- [x] 21. Define role-agent memory: goals, fears, knowledge, emotion, relationships and voice. → `role-actor` 内置 profile，系统提示明确要求读取角色卡再以角色身份输出（情绪/动机/对话/行动意图）。
- [x] 22. Define director/天意 agent: theme, conflict, pacing, external events and world-rule constraints. → `divine-director` 内置 profile，输出结构化指令（冲突/节奏/世界事件/角色调度/钩子）。
- [x] 23. Define editor agent: logic, character consistency, pacing, hook strength and imageability review. → `story-editor` 内置 profile，五维度检查（逻辑/一致性/节奏/钩子/可画面化）+ 逐条修改建议 + 全局评分。
- [x] 24. Build MVP scene simulation: director asks role agents for reactions, editor reviews, writer turns it into scene outline. → `MultiAgentCoordinator` 服务 + `POST /agent/multi-agent/scene-simulation` API，流水线：天意导演→角色演员→编辑润色→创作导演合成。
- [x] 25. Store simulation output as candidate chapter outline/script versions, not as automatic final content. → 保存为独立 `scene_simulation_candidate` 内容，带 `candidate=true` / `approved=false`，不覆盖正式正文。

## Phase 6: Canvas and Traceability

- [x] 26. Add project canvas nodes for bible, world cards, character cards, scene cards, panels, prompts and images.
- [x] 27. Add edges for contains, uses, references, derives and revises.
- [x] 28. Use asset lineage where possible to show generated-image relationships.
- [x] 29. Add export manifest containing project JSON, prompts, linked assets and lineage.

## Verification

- [x] 30. Verify a character portrait can be generated, linked and reused by a storyboard panel.
- [x] 31. Verify a storyboard panel prompt includes character, scene, world and style context.
- [x] 32. Verify batch generation can skip existing images and continue after a failed panel.
- [x] 33. Verify project bible/world assets influence chapter outline generation.
- [x] 34. Verify multi-agent MVP output can be saved as a candidate version without overwriting approved content.
