# Tasks

## Phase 0: Audit and Contract

- [x] 1. Inventory /story sections, handlers, loading states and persistence keys; map project-level and chapter-level ownership.
- [x] 2. Confirm current API/data ownership and that redesign introduces no duplicate project facts.
- [ ] 3. Define responsive breakpoints, keyboard focus order and minimum readable widths.
- [ ] 3.1 Define the resume and next-step heuristic from existing persisted facts, including deterministic fallback when a saved chapter/stage is missing.
- [ ] 3.2 Define stable user-facing chapter states and map them from existing content, lock, review and task records.
- [ ] 3.3 Define the decision-ledger evidence contract and accept/defer/reject behavior; recommendations must remain advisory and auditable.
- [ ] 3.4 Define the compact continuity summary for prose/storyboard stages and its narrow-screen behavior.

## Phase 1: Information Architecture

- [x] 4. Add explicit overview and chapter-studio workspace modes without changing business APIs.
- [ ] 5. Group outline, project bible, chapter plan, characters, assets and graph into collapsible overview sections.
- [x] 6. Move chapter-specific content into a dedicated chapter studio with compact chapter navigation.
- [ ] 7. Preserve user collapse state per project and open only the relevant section/stage by default.
- [ ] 8. Move advanced JSON, batch actions, export and destructive actions behind menus/inspector.

## Phase 2: Implementation

- [ ] 9. Split frontend/src/pages/story/index.tsx into reviewable UI components while retaining handlers.
  - 2026-09-11: 物理拆分主体完成，index.tsx 13167 -> 4454 行（-66%）。新增 story/types.ts（36 个类型）、story/styles.ts（55 个样式常量/工厂）、story/utils.ts（86 个纯函数）、story/components/ 下 10 个按域拆分的组件文件（35 个组件）、story/hooks/useStoryLayout.ts。全程 `npx tsc --noEmit` 与 `npm run build` 通过，无循环依赖。
  - 2026-09-11: 剩余两件事。(1) StoryPage 逻辑区（约 3060 行）继续抽 hook：数据加载群（约 20 个 load 函数 + 30 个 state）、内联生图（handleInlineGenerateImage 185 行 + finalizeInlineImageResult 105 行）、生成动作群；(2) 1207 行 JSX 渲染主体拆成子组件（需设计 props 传递）。
- [ ] 10. Implement overview summary, ResumeWorkspace, actionable empty states, stage progress, chapter production queue and recent activity.
- [ ] 11. Implement chapter studio navigation, stage tabs, context inspector and generation trace.
- [ ] 12. Restore project/mode/chapter/stage after refresh without duplicate data.
- [ ] 13. Add loading, error, disabled, focus, unsaved and save-failed states.
  - 2026-08-09: Story default loading no longer blocks on Writer Room history. The workspace loads only current stage outputs; `include_history=true` is fetched on entry to Writer Room and refreshed after Writer Room mutations.
  - 2026-08-09: The content API accepts an optional `content_types` filter. Story overview requests production types only, excluding large Writer Room candidate/review payloads from the initial response.
  - 2026-08-12: Writer Room refresh filters to candidate types and preserves visible data on auxiliary refresh failure. Batch responses include persisted successful candidates in `results_contents`; the UI merges them immediately and refreshes logs/content asynchronously.
  - 2026-08-12: Writer Room now reads latest candidates for the project plus history only for the selected chapter. Candidate loading has its own visible failure/retry state instead of falling through to the empty "not generated" state.
  - 2026-08-12: Writer Room candidate requests are generation-guarded. A stale response from a prior chapter, project or retry cannot overwrite the currently inspected chapter's candidates, loading flag or error state.

## Phase 3: Visual System

- [ ] 14. Apply existing dark workbench palette with one action accent and consistent typography/spacing.
- [ ] 15. Remove redundant cards, oversized empty surfaces, repeated model selectors and permanent auxiliary panels.
- [ ] 16. Verify 1440px, 1280px and mobile widths; fix overflow, wrapping and focus order.

## Phase 4: Verification

- [ ] 17. Run focused story backend tests and frontend type/build checks.
- [ ] 18. Use external Chrome/Patchright for overview -> chapter studio -> generation -> saved result.
- [ ] 19. Verify API surface unchanged; regenerate API docs if routes change.
- [ ] 20. Update DESIGN.md and system architecture; archive only after acceptance.
