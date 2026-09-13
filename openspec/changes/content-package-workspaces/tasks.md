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
- [x] 15. Add WeChat, Xiaohongshu, Douyin, PDF and Asset Bundle adapter outputs without duplicating source package items.
  - _2026-09-14 完成（后端 + API；界面触发按钮未做，见文末说明）：_
    - _新增 `backend/app/services/creative_project/content_package_adapters.py`：五个**纯函数**适配器，把同一份内容包翻译成各平台形状——`wechat_official_account`（HTML+标题+摘要+封面/正文配图引用+草稿 payload 形状）、`xiaohongshu_carousel`（3:4 竖版卡片、页序、标签）、`douyin_short_video`（9:16 镜头表+口播/字幕+视频参数）、`pdf_ebook`（分页结构+文件名）、`asset_bundle`（package.json / content.md / prompts.tsv 三件套）。_
    - _职责边界（design §4）：不调外部平台、不写回源包、不保存第二份事实源。**"不复制 items"的准确含义**：平台产物必然包含正文文字（那是产物本身），禁止的是把 items 整体再存一份当作可编辑事实源；因此每条输出都带 `source_package_id` / `source_package_version` / `source_item_ids`，"源包改了、输出过期了"可判定。已有测试断言输出记录不含 `items` 键、逐条产物必须带 `item_id` 回引。_
    - _失败语义：**单个适配器抛错不影响其它适配器**（该条记 `status="failed"` + `error`，其余照常产出，可独立重建）；未知适配器名在构建前抛 ValueError（端点转 400）。_
    - _新增端点 `POST /api/v1/creative-projects/{project_id}/content-package/outputs`（已同步 `docs/architecture/API_SURFACE.md`）：`{adapters, save}`，`save=true` 时把 outputs 追加为**新包版本**（旧版本不可变）——界面「输出适配」检查项以 `outputs` 非空为依据，因此必须落库才能变绿。响应另带 `available_adapters`（适配器目录含 label 与 planning_only），前端无需硬编码名字。_
    - _两处如实标注的**能力缺口**（不掩盖）：① `douyin_short_video` 与 `pdf_ebook` 标记 `planning_only=True`，输出中带 warning 说明"只产出规划数据"——抖音的视频由后续步骤生成（用户已确认此范围），PDF 的字节需要有渲染器（**本环境未装任何 PDF 生成库**，仅 `pypdf` 可读写/合并，无法从零排版）；② 后端**不解析 asset_ids → URL**（`to_asset_download_url` 收的是文件路径而非资产 id，逐个查 Asset Hub 会引入 IO 与耦合），因此产物只带 `image_asset_ids`，由前端解析；公众号 HTML 在无 URL 时**不静默少图**，改为输出 `<img data-asset-id="...">` 占位供渲染方替换。_
    - _验证：`test_content_package_adapters.py` **13 例**（五适配器齐备+溯源齐全、无 items 副本、失败隔离、未知适配器报错、各平台形状、HTML 转义、asset 占位、URL 注入）；`test_creative_project_workflow_api.py` 新增集成测试 1 例（产出→落为新版本→未知适配器 400→无内容包 400）。回归 `pytest -k "content_package or creative_project or profile or workflow or adapter"` → **204 passed**。_
    - _未做（明确划界）：**前端触发入口**。当前只有 API 可调用，内容包工作台没有「生成平台输出」按钮，所以界面上「输出适配」那盏灯**不会自己变绿**——需要前端调这个新端点。这属于前端工作（design §6 的输出栏），我把它留给 #14/#19，或你要我现在补。_
    - _2026-09-14 **用户复核后纠正两处设计偏差**（原实装的问题，均已改）：_
      - _**① 不该按平台命名适配器**：原实装叫 `douyin_short_video`，但全仓核对发现——该名字**只出现在 design §4 一句与我自己的代码里，没有任何方案声明它**；而项目既有 `connectors/base/social_base.L35 SHORT_VIDEO = "short_video"` 已经是通用口径。短视频平台（抖音/快手/视频号）导出结构本就同一套，差异属发布环节。已改名 **`short_video`**，并在模块内写明"按产出形态命名，不按平台命名"，design §4 同步更正。_
      - _**② 输出集合应由方案声明决定，而非调用方硬传**：原端点要求显式传 `adapters`，等于 `profiles.py` 的 `output_adapters` **依旧无人消费**。已改为**不传时取该项目内容生产方案的 `output_adapters` 全出**（页书→pdf+素材包；科普/平台图文→公众号+小红书+素材包；单镜头→素材包），这也让 `output_adapters` 第一次真正成为运行时依据。新增测试断言"不传 adapters 时按方案全出"。_
- [ ] 16. Add project-to-package and standalone-package-to-project attachment flows through Asset Hub and project content links.
- [ ] 17. Update Agent Director routing so package plans use content cards/items and full narrative plans use existing stages.

## Phase 5: Verification and docs

- [ ] 18. Add backend tests for profile routing, package schema, planner compatibility, item rerun and adapter output provenance.
- [ ] 19. Add frontend build and browser smoke for a zodiac picture book and knowledge cards; defer article/carousel smoke until their UIs are enabled.
- [ ] 20. Verify batch generation enters task center, event logs and Asset Hub with per-item provenance and independent retry.
- [ ] 21. Update system architecture, API Surface, creative workflow Skill and external-agent examples when the first endpoint is implemented.
