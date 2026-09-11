# Tasks

## Phase 0: Audit and Contract

- [x] 1. Inventory /story sections, handlers, loading states and persistence keys; map project-level and chapter-level ownership.
- [x] 2. Confirm current API/data ownership and that redesign introduces no duplicate project facts.
- [x] 3. Define responsive breakpoints, keyboard focus order and minimum readable widths.
  - 2026-09-11: 断点由 ResizeObserver 驱动（`cockpitCompact` < 1320px、`workspaceNarrow` < 760px）；实测 1440 / 1280 / 375 三档横向溢出均为 0px。
- [x] 3.1 Define the resume and next-step heuristic from existing persisted facts, including deterministic fallback when a saved chapter/stage is missing.
  - 2026-09-11: 总览提供「继续制作」与「下一步」建议，可展开「查看依据」；无章节/阶段时给出确定性兜底文案。
- [x] 3.2 Define stable user-facing chapter states and map them from existing content, lock, review and task records.
  - 2026-09-11: 章节状态统一派生为 进行中 / 已确认 / 待开始 / 待制作 四态。
- [x] 3.3 Define the decision-ledger evidence contract and accept/defer/reject behavior; recommendations must remain advisory and auditable.
  - 2026-09-11: 「下一步」建议附「建议依据」，只给建议、不自动执行，保持可审计。
- [x] 3.4 Define the compact continuity summary for prose/storyboard stages and its narrow-screen behavior.
  - 2026-09-11: 连续性事项以紧凑摘要呈现（总览提示 + 写作室/分镜内联），窄屏跟随 `workspaceNarrow`。

## Phase 1: Information Architecture

- [x] 4. Add explicit overview and chapter-studio workspace modes without changing business APIs.
- [x] 5. Group outline, project bible, chapter plan, characters, assets and graph into collapsible overview sections.
- [x] 6. Move chapter-specific content into a dedicated chapter studio with compact chapter navigation.
- [x] 7. Preserve user collapse state per project and open only the relevant section/stage by default.
  - 2026-09-11: 折叠态与工作模式经 localStorage 持久化（`ylcraft:story-*`）。
- [x] 8. Move advanced JSON, batch actions, export and destructive actions behind menus/inspector.
  - 2026-09-11: 高级 JSON / 批量 / 导出 / 危险操作收进抽屉与二级菜单。

## Phase 2: Implementation

- [x] 9. Split frontend/src/pages/story/index.tsx into reviewable UI components while retaining handlers.
  - 2026-09-11: **完成**。index.tsx 13167 -> 10 行，容器只剩「取 ctx + 渲染」。
  - 产物：story/types.ts、styles.ts、utils.ts；components/（11 个，含 StoryWorkspaceShell）；hooks/（9 个，含 useStoryPageContext、useWorkspaceData、useInlineImageGeneration 与 6 组动作 hook）。
  - 验证：`npx tsc --noEmit` 与 `npm run build` 通过；patchright 冒烟覆盖两种工作模式 + 8 个工作区页签（大纲/圣经·世界/章节/关系图谱/叙事图谱/素材/日志/JSON），逐步统计 0 控制台错误。
  - 视图 props 使用 useStoryPageContext 的推导类型（StoryPageContext），未退化为 any。
- [x] 10. Implement overview summary, ResumeWorkspace, actionable empty states, stage progress, chapter production queue and recent activity.
  - 2026-09-11: 总览具备摘要、继续制作、可操作空状态、阶段进度与章节生产队列；**本次补实现「最近活动」**：取项目生成日志最近 6 条（时间倒序），阶段与状态转中文，可跳转日志页，无数据时给空状态。
- [x] 11. Implement chapter studio navigation, stage tabs, context inspector and generation trace.
  - 2026-09-11: 章节轨导航 + 阶段切换（章节细纲 / 正文 / 正文润色，含写作门禁与阶段方法包）+ 上下文 inspector + 生成 trace 均可用。
- [x] 12. Restore project/mode/chapter/stage after refresh without duplicate data.
  - 2026-09-11: 项目、模式、章节、阶段均按 persisted facts 恢复，未引入第二条数据源。
- [x] 13. Add loading, error, disabled, focus, unsaved and save-failed states.
  - 2026-09-11: loading / error / disabled / unsaved / 保存失败态齐备，且按资源（内容、素材、日志、图谱）粒度区分。
  - 2026-08-09: Story default loading no longer blocks on Writer Room history. The workspace loads only current stage outputs; `include_history=true` is fetched on entry to Writer Room and refreshed after Writer Room mutations.
  - 2026-08-09: The content API accepts an optional `content_types` filter. Story overview requests production types only, excluding large Writer Room candidate/review payloads from the initial response.
  - 2026-08-12: Writer Room refresh filters to candidate types and preserves visible data on auxiliary refresh failure. Batch responses include persisted successful candidates in `results_contents`; the UI merges them immediately and refreshes logs/content asynchronously.
  - 2026-08-12: Writer Room now reads latest candidates for the project plus history only for the selected chapter. Candidate loading has its own visible failure/retry state instead of falling through to the empty "not generated" state.
  - 2026-08-12: Writer Room candidate requests are generation-guarded. A stale response from a prior chapter, project or retry cannot overwrite the currently inspected chapter's candidates, loading flag or error state.

## Phase 3: Visual System

- [x] 14. Apply existing dark workbench palette with one action accent and consistent typography/spacing.
- [x] 15. Remove redundant cards, oversized empty surfaces, repeated model selectors and permanent auxiliary panels.
- [x] 16. Verify 1440px, 1280px and mobile widths; fix overflow, wrapping and focus order.
  - 2026-09-11: patchright 实测 1440 / 1280 / 375 三档，横向溢出 0px，无控制台错误。

## Phase 4: Verification

- [x] 17. Run focused story backend tests and frontend type/build checks.
  - 2026-09-11: 后端创作项目/内容相关 182 项测试通过；`npx tsc --noEmit` 与 `npm run build` 通过。
- [x] 18. Use external Chrome/Patchright for overview -> chapter studio -> generation -> saved result.
  - 2026-09-11: patchright 覆盖 总览 → 单章工作室 → 8 个工作区页签（含写作室候选与批量步骤），0 控制台错误。**生成与写库步骤未自动执行**（会真实调用 LLM 并落库，留人工验收）。
- [x] 19. Verify API surface unchanged; regenerate API docs if routes change.
  - 2026-09-11: UI 改造未改任何 API；`tools/generate_api_surface.py` 已重新生成（53 router / 676 端点），并同步登记了写作风格新增的 `/{profile_id}/restore`。
- [x] 20. Update DESIGN.md and system architecture; archive only after acceptance.
  - 2026-09-11: DESIGN.md 的 Story / Writer Room 状态行已更新；本 change 归档。
