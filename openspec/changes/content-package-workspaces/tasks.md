# Tasks

## Phase 1: Contract and routing (first implementation slice)

- [x] 1. Define `content_package` JSON contract, package types, item status, source references, outputs and stable item ids; freeze the contract before UI work.
- [x] 2. Extend content-production profiles with `production_family`, `package_type`, `required_inputs`, `optional_inputs`, `planning_unit` and `output_adapters`.
- [x] 3. Add routing rules so full narrative profiles keep `/story` and lightweight profiles open the content-package workspace; preserve legacy profile fallback.
- [x] 4. Add focused validation for package types, minimum inputs, source-only planning and profile compatibility.
- [x] 5. Decide and document standalone draft persistence (`content_package_drafts` or an existing draft service) before adding any endpoint.

## Phase 2: Shared planner and persistence

- [x] 6. Extract the reusable planner from `outline_service.py` while preserving `/images/generate-outline` response compatibility.
  - _2026-09-13 完成：_
    - _新增 `backend/app/services/ai/content_package_planner.py` 的 **`ContentPackagePlanner`**：`plan_platform_outlines()`（平台模板驱动的大纲规划，等价迁移原 `generate_outline` 全部行为，含逐平台兜底结构与 `asyncio.gather` 并发）、`parse_structured_text()`（原 `_parse_outline_text` 逐行等价）、`render_template_prompt()` / `build_outline_messages()`（含多模态分支）、以及**新增**的 `platform_outlines_to_package()` 与 `plan_package()` —— 把平台大纲按「一页 ⇒ 一个 item」转换为内容包契约，使内容包路径可复用同一套规划而不必另写 LLM 调用与解析。_
    - _`outline_service.py` 改为**兼容层**：`generate_outline`（322 行文件里的 ~112 行实现 → 39 行委托）签名与返回值结构**逐字段不变**；`_parse_outline_text` 保留为兼容别名；`batch_generate_images` **原样未动**（规划与生成分离，内容包路径只复用规划、不连带触发消耗型操作）。_
    - _兼容面核实：`_parse_outline_text` 全仓无外部引用（模块私有）；`generate_outline` 由 `api/v1/images.py` 的三处调用（`/images/generate-outline` 与两处批量入口）使用，均为延迟导入，签名不变即无需改动。_
    - _测试：新增 `backend/tests/test_content_package_planner.py`（8 例）——覆盖①响应结构不变（title/copywriting/pages/platform/platform_name 与 pages 的 type/prompt 层级）、②wrapper 委托后无模板返回 `{}`、③`_parse_outline_text` 别名可用、④单平台失败仍保留兜底结构且不影响兄弟平台、⑤一页⇒一item 且键集固定、⑥失败平台只进 `warnings` 不伪造 item、⑦空输入产出空包、⑧多模态消息构造。实测 **8 passed**；回归 `pytest -k "outline or image or planner or ai_backend or content_package or platform"` → **115 passed**。_
- [x] 7. Add the minimum content-package plan/read/update/version APIs using `ProjectContent` for project-bound packages and the approved standalone draft path.
- [ ] 8. Add item-level stale/retry semantics and preserve package/item/asset provenance in requests and task payloads.
- [ ] 9. Add API-facing Skill and Agent tool contracts for planning, item editing and package inspection.

## Phase 3: Lightweight workspaces (only two package types initially)

- [x] 10. Build a reusable content-package workspace shell instead of reusing the full story blueprint form.
- [ ] 11. Implement `page_book` for picture books/comics with page text, image prompts, batch image generation and optional layout.
- [x] 12. Implement `knowledge_cards` with topic intro, fact/source placeholders and prompt-only mode.
- [x] 13. Add the article-package, carousel, shot-list and single-media schemas behind feature flags or API-only routes; do not build four new UIs in the first slice.
  - _2026-09-13 完成（API-only，未建任何 UI）：_
    - _新增 `backend/app/services/creative_project/content_package_schema.py`：把 **六种** `package_type` 的契约集中声明为 `PackageSchema`（条数边界、item 字段、包级字段、默认媒体、`ui_enabled`）。此前 `save_content_package` 只校验「包类型与 profile 一致 + items 是对象数组」，后四种类型**没有任何契约**，API 调用方无从知道该给什么。_
    - _`ui_enabled` 即"本期只做 API、不建 UI"的**开关标记**：`page_book` / `knowledge_cards` 为 true，`article_package` / `social_carousel` / `shot_list` / `single_media` 为 **false**。_
    - _**校验刻意分两档**（因为生成是 LLM 驱动的，把"缺字段"一律当硬错误会让一次模型抖动直接变成保存失败）：硬错误仅限结构性不可落库的问题——未知包类型、items 非数组、item 非对象、`status` 不在七态取值域、条数超上限；软提示收 `warnings`——条数低于推荐下限、个别 item 缺推荐字段、整包无任何媒体提示词。_
    - _保存路径接入：`save_content_package` 按类型校验；包的 `data` 里新增 `schema`（含 `version`，便于 schema 演进后判断历史包按哪一版校验）与 `warnings`。_
    - _**一处必须修掉的回归风险**：`generate_content_package` 原为 `count = min(item_count or 12, 80)`，而 `single_media` 上限是 1 条——单镜头项目生成 12 条后保存必被按类型拒绝（"生成成功但保存失败"）。改为按 schema 夹住数量，使 schema 成为唯一权威。_
    - _**一次"过严"的自我纠正**：初版把「整包无任何媒体提示词」当硬错误，结果打挂既有用例 `test_content_package_api_versions_and_rejects_narrative_projects`——它保存的是「只有标题、尚未写提示词」的中间态版本，而"先存标题再补提示词"是内容包增量编辑的正常用法。已降为 warnings。_
    - _测试：新增 `backend/tests/test_content_package_schema.py` **18 例**（六类型齐备、四种 API-only 的 ui_enabled 为 false、未知类型报错、超上限/status 非法为硬错误、无提示词只提示、条数偏低与缺字段只提示、按生成路径实际形状构造的干净包零提示、空包不误报）。回归 `pytest -k "content_package or creative_project or profile or workflow"` → **189 passed**。_

## Phase 4: Platform adapters and migration

- [ ] 14. Move existing multi-platform generation UI logic into reusable package/adapter components while keeping `/multi-platform-gen` as a compatibility entry.
- [ ] 15. Add WeChat, Xiaohongshu, Douyin, PDF and Asset Bundle adapter outputs without duplicating source package items.
- [ ] 16. Add project-to-package and standalone-package-to-project attachment flows through Asset Hub and project content links.
- [ ] 17. Update Agent Director routing so package plans use content cards/items and full narrative plans use existing stages.

## Phase 5: Verification and docs

- [ ] 18. Add backend tests for profile routing, package schema, planner compatibility, item rerun and adapter output provenance.
- [ ] 19. Add frontend build and browser smoke for a zodiac picture book and knowledge cards; defer article/carousel smoke until their UIs are enabled.
- [ ] 20. Verify batch generation enters task center, event logs and Asset Hub with per-item provenance and independent retry.
- [ ] 21. Update system architecture, API Surface, creative workflow Skill and external-agent examples when the first endpoint is implemented.
