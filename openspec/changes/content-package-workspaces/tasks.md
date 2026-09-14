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
- [x] 8. Add item-level stale/retry semantics and preserve package/item/asset provenance in requests and task payloads.
  - _2026-09-14 完成（后端 + 前端入口）：_
    - _新增 `POST /api/v1/creative-projects/{project_id}/content-package/items/{item_id}/retry`：**只重跑一条**内容单元的文本/提示词，其余条目原样保留（不重新规划整包——省 token，也不会冲掉用户已手改好的条目）。用 `ContentPackageItemSchema` 作为输出契约；条目不存在返回 400。_
    - _**stale 语义按依赖判定**：新增 `mark_outputs_stale(outputs, changed_item_ids)`——只有 `source_item_ids` 命中变更条目的输出被标 `stale`，其余保持 `ready`。__一处必须说清的事实__：当前五个适配器都产出**整包级**产物（公众号整篇、整册 PDF、整包素材），它们的 `source_item_ids` 都是全部条目，**因此改任一条都会让全部输出过期**——这是依赖判定得出的正确结论，不是无差别作废；将来若出现条目级产物，同一机制只会影响相关部分。_
    - _溯源（design §5.2）：重试时任务载荷带上 `package_id` / `package_version` / `item_id` / `item_retry`，任务中心与事件日志可回溯到具体条目；已有测试断言这四个字段。_
    - _**一处语义冲突的自我纠正**：初版把"输出已过期"追加进包的 `warnings`，但 `save_content_package` 会用 schema 校验结果**整体覆盖** `warnings`，导致提示丢失（被测试抓到）。改为**过期信息只落在 outputs 自身**（`status` + `stale_reason`）——`warnings` 保持"契约校验提示"这一稳定语义，状态性信息混进去既会被覆盖、又会在重新产出输出后残留成误导。_
    - _前端：内容包编辑器每条加「**重跑本条**」按钮（表单里未保存过的新行没有 id，会提示先保存）；「平台输出」区块加「**生成平台输出**」按钮 + 输出列表（状态标签 已生成/已过期/失败、条数摘要、导出 JSON，素材包三件套逐个可下载）。_
    - _测试：`test_content_package_adapters.py` 13 例（含 `mark_outputs_stale` 行为）；`test_creative_project_workflow_api.py` 新增集成测试——单条重试后**目标条目被重写、兄弟条目原样保留**、引用它的输出全部 stale 且带 `stale_reason`、不存在条目 400。_**真实浏览器验收 13/13**（1600×1000）：生成平台输出产出「PDF 电子书 + 素材包」、状态「已生成」、三件套可下载、**绘本方案不含公众号/小红书/短视频**（证明按方案清单出）、刷新后仍在（已落库）、0 个 >=400、0 条控制台 error。_
- [x] 9. Add API-facing Skill and Agent tool contracts for planning, item editing and package inspection.
  - _2026-09-14 完成（Skill 侧见 #21，本条补 Agent 工具契约）：_
    - _新增 **6 个** Agent 工具（`services/agent/tools/creative_project_tools.py`），三类职责齐全：_
      - **检视**：`get_content_package`（`read`）—— 读最新包或按版本倒序读历史；无包时返回 `None` 而非报错，调用方据此判断"还没生成"。_
      - **规划**：`plan_content_package`（`costly`）—— 按主题/素材一次生成内容包并落版本；不产图、不访问外部平台。_
      - **条目编辑**：`update_content_package_item`（`write`，手工改单条，**不调模型**）与 `retry_content_package_item`（`costly`，让模型只重跑一条）。_
      - **另补两个闭环入口**：`save_content_package`（`write`，写入用户提供或智能体整理好的整包）与 `build_content_package_outputs`（`write`，本地格式翻译）。_
    - _**风险等级按"是否产生消耗"划分，而非按"是否写库"**：读 1 个、写 3 个、消耗 2 个。纯写入（改条目/存包/出适配产物）不需要模型也不访问外部平台，但仍会改变项目内容，因此仍需确认；只有会调用文本模型的两个才标 `costly` 并给出 `cost_hint`。_
    - _**一处必须处理的语义缺口**：`save_content_package` 只做契约校验，**不会**标记输出过期。若 `update_content_package_item` 直接复用它，手工改条目后旧的平台输出会**仍显示为可用**——与本 change 的 `stale` 承诺相矛盾（`retry_content_package_item` 走 service 层会标，手工改不会，两者结论不一致）。因此该工具显式复用同一份 `mark_outputs_stale`，使两条路径得到同一结论；测试专门固定这一点。_
    - _注册链路四处同步：`tools/__init__.py` 的导入块 + `TOOLS` 列表 + `__all__`，以及 `profile.py` 中 `creative-director` 的 `allowed_tools`。**注册了但未授权等于不可用**，故测试同时断言授权。_
    - _测试：新增 `backend/tests/test_content_package_agent_tools.py`（**12 例**）——六工具注册与风险分级、创作导演授权、消耗型与纯写入分离且带成本提示、读最新与历史、无包返回 None、**按条目改只动一条且只让引用它的输出过期**（含"输出只依赖另一条时不得被作废"的按依赖判定）、缺字段与未知条目明确报错、`status` 越界被契约挡住、`save=False` 预览不落库、不传 adapters 时按方案声明出 `pdf_ebook`+`asset_bundle` 且每条带溯源。_
    - _测试另加一条性质固定：这些读/写路径**都不应调用模型**——用会抛错的假 AIService 顶替，一旦被调用即失败。_
    - _过程中我犯过一次错并已修正：追加工具块时缩进写错导致 `IndentationError`，先用补丁式去缩进反而误伤块内次级缩进，最终改为「保留到 `run_creative_writer_room` 收尾、整块按正确缩进重写」，`py_compile` 与实测均通过。_
    - _验证：`pytest tests/test_content_package_agent_tools.py` → **12 passed**；回归 `pytest -k "agent or content_package or creative_project or tool or profile"` → **359 passed / 2 skipped**；lints 干净。_

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

- [x] 14. Move existing multi-platform generation UI logic into reusable package/adapter components while keeping `/multi-platform-gen` as a compatibility entry.
  - _2026-09-14 完成：_
    - _新增 `frontend/src/components/content-package/`（两处原先各自内联实现，现共用一份）：_
      - **`GeneratedMediaThumb.tsx`** —— 媒体生成结果缩略图。取代 `/multi-platform-gen` 页卡里内联的 **133 行**结果块：有图给「图片 + 悬浮（重新生成 / 删除）」，无图给「虚线占位 + 失败原因 + 渐变重试」。_
      - **`PackageOutputList.tsx`** —— 适配器输出列表。取代内容包工作台内联的 **59 行**输出块：状态三态（`ready`→已生成/绿、`stale`→已过期/橙、其余→失败/红）、payload 摘要（卡片数/镜头数/页数/文件数）、导出 JSON、素材包逐文件下载、error 与 warnings 分行。它描述的是通用适配器契约，与具体包类型无关。_
    - _**一处真问题被顺带修掉**：内容包条目**从不展示生成结果**——`image_url` / `asset_ids` / `status` 早就由生成链路写回表单（见 `useProjectContentActions.handleBatchGenerateContentPackageImages` L356-360），界面却什么都不显示，用户生成完看不到图。现已接上结果位（`Form.Item shouldUpdate` 触发，批量/单条生成写回后立即反映）。**无图时不传 `onRegenerate`**：占位态按钮文案是「重试」，而这些条目还没生成过，上方已有「生成图片」，不该出现语义不符的重复入口。_
    - _**`downloadTextFile` 下沉**：原在 `pages/story/utils.ts`，但它与 Story 页面无关，共享组件反向依赖页面模块是错误方向。已移至 `utils/download.ts` 并在原处 re-export，既有 4 处调用零改动。_
    - **兼容入口保持**：`/multi-platform-gen` 路由与页面签名未变，只是内部改为组合共享组件；实测页面正常打开、含「主题」「生成大纲」。_
    - _**一处刻意的视觉修正（如实记录）**：`/multi-platform-gen` 悬浮按钮原先渲染的是孤立的字面量 `C`（`title` 已是"重新生成"，内容显然是被吞掉的图标）。抽组件时统一换成 `ReloadOutlined`。这是本条唯一一处非纯搬运的视觉改动。_
    - _清理死导入：`MultiPlatformGen` 的 `ReloadOutlined`、`StoryWorkspaceShell` 的 `downloadTextFile` 在替换后仅剩导入行。**注意 tsconfig 关了 `noUnusedLocals`，tsc 不会报死导入**，因此我用脚本按「标识符是否只出现在导入行」单独扫过（3 个文件均 0 死导入）。_
    - _验证：`npm run build` 通过（3824 模块，较上次 +3，与新增的 2 个组件 + 1 个工具一致）；`npm test`（vitest）**4 文件 39 例通过**；lints 干净。**浏览器 smoke**：`/multi-platform-gen` 正常；内容包工作台的平台输出由新组件渲染且信息不丢（「PDF 电子书」×2、「素材包」×2、「导出 JSON」×2 对应真实的 2 条输出）、条目结果位按预期显示（「尚未生成」×2，该项目 2 条都还没有图）；**0 个 >=400、0 条控制台 error、0 项断言失败**。_
    - _**一个既有的工具链缺口（非本次引入）**：`npm run lint` 跑不起来——`frontend/` 下**没有任何 ESLint 配置文件**，`package.json` 也未声明 eslint 依赖，环境里的 ESLint 10 会直接报 "couldn't find an eslint.config.*"。即该脚本在**未改动的代码上同样失败**。未在本次处理（属仓库治理问题，已记入待办讨论）。_
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
- [x] 17. Update Agent Director routing so package plans use content cards/items and full narrative plans use existing stages.
  - _2026-09-14 完成：_
    - _**缺口定位**：`context_pack.py` 会把 `production_profile.recommended_stages` **原样**交给导演（无族别判断），而内容包族的四个 profile 当时写的却是**叙事阶段**——`storybook` 是 `["outline","chapter_plan","chapter_outline","script","storyboard","comic_pages"]`。也就是导演拿到一个绘本包项目时，被引导去提议章节大纲与细纲。这正是本条要修的路由错误。_
    - _**词表按族拆分**：`profiles.py` 新增 `PACKAGE_PLAN_STAGES = (package_plan, item_text, item_prompt, media_batch, package_outputs)`，每个阶段都**对应一个已落地能力**（分别是 `POST .../content-package/plan`、条目文本、条目提示词、批量媒体任务、`POST .../content-package/outputs`），不是构想。四个内容包 profile 改用该词表（`platform_note` 因 `planning_unit=package` 用 `package_plan→item_text→package_outputs`，媒体阶段归可选；`single_shot` 用 `package_plan→item_prompt→media_batch`）；**叙事族 `vertical_drama` / `novel_serial` 的阶段逐字未动**。_
    - _**让族别可自查**：Context Pack 的 `production_profile` 块新增 `production_family` / `package_type` / `planning_unit`（原先只有 id/label/stages）。只给阶段名而隐藏族别，"为什么该按这些阶段走"无法自查——这正是原来那个错误能长期存在的原因。_
    - _**刻意的设计选择：词表是路由输入（指导），不是校验器**。计划节点的 `stage` 仍是自由字符串，未知值不被拒绝——既有测试与真实计划里就存在 `stage="image"` 这类自定值，硬校验会打断它们。这与本 change 在 schema 上的"两档校验"同一取向：结构性问题才硬拒。_
    - _测试：`test_content_production_profiles.py` 由 6 例扩到 **9 例**（`storybook` 走内容包阶段且不含任何叙事阶段、两个叙事 profile 阶段逐字不变且与内容包词表无交集、**所有**内容包 profile 的阶段都落在声明词表内（防以后顺手写 `outline`）、词表内容与已落地能力一一对应）；`test_creative_project_workflow_api.py` 扩展既有 context pack 用例断言族别/包类型/编排单位/阶段，并**新增一条叙事族对照**用例（`vertical_drama` 仍为既有阶段、与内容包词表无交集）。_
    - _文档：架构 §4.4.6 新增第 4 条说明两族阶段词表的区别与"指导而非校验"的取向；API-facing Skill 的 `SKILL.md` 与 `references/api-workflows.md` 补「Plan stages by production family」对照表，明确不要给绘本包提议章节大纲。_
    - _验证：profile 测试 **9 passed**；context pack 两条 **2 passed**；回归 `pytest -k "profile or context_pack or creative_project or content_package or agent or pipeline or production"` → **363 passed / 2 skipped**；lints 干净。_

## Phase 5: Verification and docs

- [x] 18. Add backend tests for profile routing, package schema, planner compatibility, item rerun and adapter output provenance.
  - _2026-09-14 **核实为已满足**：本条点名的五块逐块有覆盖（其中四块是本 change 前几轮随实现补的）——_
    - **profile routing**：`tests/test_content_production_profiles.py`（方案定义与 `get_content_production_profile`）+ `test_creative_project_workflow_api.py::test_content_package_api_versions_and_rejects_narrative_projects`（方案路由到端点、且拒绝叙事方案走包端点）。_
    - **package schema**：`tests/test_content_package_schema.py` —— **14 例**（六种类型契约、硬错误 vs 软提示两档、条数上限夹取、`ui_enabled`）。_
    - **planner compatibility**：`tests/test_content_package_planner.py` —— **8 例**（含「响应结构逐字段不变」、「`_parse_outline_text` 别名可用」等兼容性断言）。_
    - **item rerun**：`test_creative_project_workflow_api.py::test_content_package_item_retry_rewrites_one_item_and_stales_outputs`（只重写一条、其余原样保留、引用它的输出标 `stale` 且带 `stale_reason`）。_
    - **adapter output provenance**：`tests/test_content_package_adapters.py` —— **14 例**（五适配器形状、`source_package_id`/`source_package_version`/`source_item_ids` 溯源、单适配器失败隔离）+ 端点级 `test_content_package_outputs_endpoint_builds_and_persists_adapters`。_
    - _实测：前四个文件 **46 passed**；workflow api 的内容包三例 **3 passed**。故勾选。_
- [x] 19. Add frontend build and browser smoke for a zodiac picture book and knowledge cards; defer article/carousel smoke until their UIs are enabled.
  - _2026-09-14 完成：_
    - **前端构建**：`npm run build`（`tsc --noEmit -p tsconfig.json` + `tsconfig.node.json` + `vite build`）**通过**，3821 模块、28s；仅有一条既有的 chunk 体积告警（`index` 1.7MB / `vendor` 2.8MB，非本次引入，也未阻断构建）。_
    - **浏览器 smoke（Patchright + Chromium 1600×1050，只读）**：两个真实项目——绘本「输出验收-十二生肖」（`storybook`/`page_book`，2 条 item，已产出 PDF+素材包）与新建的科普卡项目（`knowledge_content`/`knowledge_cards`，3 条 item，未产出输出）。测量值与数据**逐一对得上**，这是它比"页面能打开"更有价值的证据：_
      - 绘本：进入编辑器成功；「重跑本条」出现 **2** 次（= 2 条 item）；「生成平台输出」**1** 次；「还没有平台输出」**0** 次（因为它确实已有输出）。_
      - 科普卡：进入编辑器成功；「重跑本条」**3** 次（= 3 条 item）；「还没有平台输出」**1** 次（确实未生成过）。_
      - **全程 0 个 >=400 响应、0 条控制台 error、0 项断言失败**。_
    - **科普卡特有字段取证**（`fact`/`source` 是任务 #12 的交付物，必须证明真的渲染而非只是存在）：编辑器是表单，字段值在 `input`/`textarea` 里、`inner_text` 读不到——**这一点我一开始判断错了**（首轮用 `inner_text` 检查，误报"未渲染"；改读控件 value 后通过）。最终取证：`source` 值「中国国家博物馆」在 3 个 `<input>`（对应 3 条 item），`fact` 值「鼠对应地支「子」…」/「牛对应地支「丑」。」/「虎对应地支「寅」。」在 3 个 `<textarea>`。控件总数科普卡 **28** vs 绘本 **16**，与科普卡每卡多出 `fact`/`source`/`source_url` 一致。_
    - _article / carousel / shot_list / single_media 的 smoke 按本条要求**推迟**——它们的 `ui_enabled=false`（`#13`），当前无 UI 可测。_
    - _**一处如实标注的覆盖边界**：本次 smoke 是**只读**的，只验证工作台对已有内容的渲染与入口，**未触发**任何生成，因此"点生成 → 出图 → 回流 Asset Hub"这条消耗型链路在浏览器里未覆盖（属 `#20`，需额度）。_
    - _过程中未消耗额度：科普卡项目的包是用 `PUT .../content-package` **手工写入**的（免费），而非调用 `.../plan`（会调用模型）。_
- [ ] 20. Verify batch generation enters task center, event logs and Asset Hub with per-item provenance and independent retry.
- [x] 21. Update system architecture, API Surface, creative workflow Skill and external-agent examples when the first endpoint is implemented.
  - _2026-09-14 四处同步完成：_
    - **system architecture**（本 change 内容）：`YLCRAFT_SYSTEM_ARCHITECTURE.md` §4.4.6 新增「内容包契约三部分」——① 类型 schema 与其**两档校验**（结构性硬错误 vs 内容质量软提示，并说明为何不能把缺字段一律当硬错误：生成是 LLM 驱动的，"先存标题再补提示词"是正常中间态）；② 五个适配器与**三条边界**（不调外部平台 / 不写回源包 / 不保存第二份事实源）及"哪些适配器由方案声明决定"；③ 条目级重试与 `stale` 语义（按依赖判定）。另在 §5 平台采集行补 Cookie 规范化收在公共基类，§6 接口统计、§7 OpenSpec 状态同步。_
    - **API Surface**：跑 `tools/generate_api_surface.py` 重新生成 `API_SURFACE.md` + `api_surface.json`（53 routers / 678 endpoints）。逐端点比对 HEAD 版确认**新增 2 个端点、0 个消失**（其余为行号漂移）。_
    - **creative workflow Skill**（`#21` 点名的 API-facing Skill）：`SKILL.md` 新增「Content Packages (Lightweight)」段并更新 frontmatter description 与首段（说明该走包而非强制叙事链路、`--adapters` 省略时按方案声明出、适配器只做本地翻译、`planning_only` 不得当作成品交付、四种类型当前 API-only）；`references/api-workflows.md` 新增完整 `## Content Package (lightweight)` 段（端点与请求字段、六种包类型、五种适配器、**按 profile 的 `output_adapters` 默认表**、六条规则、命令示例）并把 `content_package` 补进 Content Types；`scripts/creative_project_workflow.py` 新增四个命令 `package-get` / `package-plan` / `package-outputs` / `package-item-retry`。_
    - **external-agent examples**：`docs/guides/external-agent-api.md` 新增「明确不在覆盖范围的端点（含内容包）」——鉴权是**逐路由声明**的（只有 9 个路由带 `require_external_api_key`），`creative_projects.py` **未声明**，故内容包等创作项目端点既不校验 Key 也不计入 scope/配额；外部 Agent 在本机可用但**不应依赖其公网可用性**，要真正对外驱动内容包需先把该路由纳入鉴权并定义作用域。**此条为如实边界标注，未把它说成已覆盖。**_
    - _验证：skill 脚本语法通过、四个新命令 `--help` 与注册正常；**真实链路实测** `package-get` 与 `package-outputs --no-save`（对项目「输出验收-十二生肖」）——未传 `--adapters` 时确按 storybook 方案产出 `pdf_ebook` + `asset_bundle` 两条，每条带 `source_package_id`/`source_package_version=2`/`source_item_ids`，`planning_only` 标记与 `--no-save` 不落库均符合设计。回归 `pytest -k "content_package or creative_project or production_profile or adapter"` → **161 passed**。_
