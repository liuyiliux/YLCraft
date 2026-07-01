# Tasks

## Phase 1: Reference Cards and Character Portraits

- [ ] 1. Define character card schema with text fields, visual fields, signature items, expressions, poses and negative constraints.
- [ ] 2. Add character portrait prompt template that outputs full copyable prompts for multi-view reference sheets.
- [ ] 3. Link generated character portraits back to project characters and asset hub nodes.
- [ ] 4. Add reference-card grouping for character, background, style, world and panel-specific references.
- [ ] 5. Let storyboard and comic image generation select project references automatically and allow manual override per panel.

## Phase 2: World Bible Assets

- [ ] 6. Split project outline into editable Project Bible sections.
- [ ] 7. Add world asset roles: map, rule, faction, location, event, power-system, economy and style.
- [ ] 8. Let chapter outline generation read locked world assets and continuity notes.
- [ ] 9. Extract new world facts and continuity deltas from generated prose.
- [ ] 10. Show world assets in the project workspace and asset hub.

## Phase 3: Storyboard Prompt V2

- [ ] 11. Extend storyboard schema with panel goal, shot size, camera angle, camera motion, composition and blocking.
- [ ] 12. Add scene card fields for location, time, weather, props, spatial axis, character positions and movement path.
- [ ] 13. Generate detailed image prompts from role cards, scene cards, camera cards and style cards.
- [ ] 14. Add full prompt preview/copy for each storyboard panel and comic page.
- [ ] 15. Add actions to rewrite only the image prompt without changing source story/script.
- [ ] 16. Add single-panel regeneration and batch panel generation with skip-existing behavior.

## Phase 4: Batch Production Queue

- [ ] 17. Add production queue UI for chapter ranges and selected stages.
- [ ] 18. Support skip existing, overwrite, retry failed and continue from failure.
- [ ] 19. Persist queue step logs with provider, model, prompt template, duration and error.
- [ ] 20. Add manual review checkpoints before expensive image generation.

## Phase 5: Multi-Agent Exploration

- [ ] 21. Define role-agent memory: goals, fears, knowledge, emotion, relationships and voice.
- [ ] 22. Define director/天意 agent: theme, conflict, pacing, external events and world-rule constraints.
- [ ] 23. Define editor agent: logic, character consistency, pacing, hook strength and imageability review.
- [ ] 24. Build MVP scene simulation: director asks role agents for reactions, editor reviews, writer turns it into scene outline.
- [ ] 25. Store simulation output as candidate chapter outline/script versions, not as automatic final content.

## Phase 6: Canvas and Traceability

- [ ] 26. Add project canvas nodes for bible, world cards, character cards, scene cards, panels, prompts and images.
- [ ] 27. Add edges for contains, uses, references, derives and revises.
- [ ] 28. Use asset lineage where possible to show generated-image relationships.
- [ ] 29. Add export manifest containing project JSON, prompts, linked assets and lineage.

## Verification

- [ ] 30. Verify a character portrait can be generated, linked and reused by a storyboard panel.
- [ ] 31. Verify a storyboard panel prompt includes character, scene, world and style context.
- [ ] 32. Verify batch generation can skip existing images and continue after a failed panel.
- [ ] 33. Verify project bible/world assets influence chapter outline generation.
- [ ] 34. Verify multi-agent MVP output can be saved as a candidate version without overwriting approved content.
