# 设计约束（AI 调用 / 任务 / 观测）

来源：`platform-event-logging`、`task-observability-diagnostics` 实现与踩坑；§8 写作风格档案来自 `creative-writing-style-profiles`。最后更新：2026-09-11。

## 1. AI 调用必须走 `AIService` 三个入口

`chat` / `generate_image` / `generate_video`（`backend/app/services/ai/service.py`）是唯一收口点：
自动落平台事件（scene/provider/model/耗时/成功失败/错误），且 `BackendRouter` 内部多次降级只算一次调用。

- 业务身份用 `ai_call_context(...)` 注入：`project_id`、`ref_id`、`scene`、`task_type`、`label`、`task_id`、`retry_payload`。
- 端点自己已写业务事件时用 `suppress_auto_event=True` 抑制自动记账，避免同一次操作落两条。
- 写日志是 best-effort：失败不打断 AI 调用本身。
- **不要回到端点手写"调用成功/失败"事件的旧模式**；那会与收口双写。
- 直连 provider 的旁路（`services/embedding` 的 httpx 直连、breaker 的 STT、model3d 的 httpx）必须自行补记事件，否则该路径不可观测。

## 2. 任务记录不能自动收口

任务需要**业务粒度**（一次"地图成图"一条），高频 `chat` 若自动建任务会冲垮任务中心。
做法：长耗时操作显式用 `ai_task(...)`（`services/ai/tracking.py`）包住
「建任务 → 记开始 → 完成或失败 → 进度与诊断」，记账失败不影响业务。

## 3. 重试/重发必须复用业务端点

- 任务重试：从账本 `request_json` 重建请求对象后，**直接 `await` 生成端点函数**（如 `await generate_video(req, external_key=None)`），
  从而复用资产入库、项目关联、事件与新任务记录的全部行为；不要另写 provider 直连逻辑。
- 事件重发：沿用 `api/v1/logs.py` 的 `retry_log` 分支结构（image/video/llm）。
- **函数直调注意**：FastAPI 端点的 `external_key: Optional[ExternalApiKey] = Depends(...)` 在直接调用时不会被解析，
  必须显式传 `external_key=None`，否则会把 `Depends(...)` 默认对象带进业务逻辑。

## 4. 前端与后端枚举必须同步

- 任务类型：后端白名单 ↔ 前端 `TASK_TYPE_OPTIONS` + `TYPE_COLOR_MAP`（缺项＝用户筛不到任务）。
- 事件场景：后端 `scene` ↔ 前端 `EventLogTab` 的 `SCENE_OPTIONS` + `SCENE_LABEL_MAP`。

## 5. 列表接口与详情接口的字段长度差异

列表/搜索接口常用 `preview=True` 截断长文本（如提示词截到 360 字），**展示全文或插入正文前必须取详情**，
否则会把残缺内容写进业务（曾导致生图提示词残缺）。

## 6. 失败链路的可观测性验收口径

回归失败链路时，四项都要成立（缺一即为观测缺口）：

1. **事件日志可见**：`GET /api/v1/logs?scene=<scene>&status=failed` 能查到该失败事件，
   详情含 `provider` / `model` / `error` / `retry_payload`。
2. **运行日志含原始输出**：`GET /api/v1/logs/runtime` 能看到 provider/SDK 原始错误
   （如 `[ERROR] [OpenAISDK-Image] OpenAI API error: ...` 与 `[WARNING] [AIService] …失败`）。
3. **可重发**：`POST /api/v1/logs/{id}/retry` 可达并产生新事件。
4. **追溯链闭合**：新事件 `retry_of` → 原事件，原事件 `retried_by` → 新事件。

实现要点：
- 脱敏复用同一个函数（`app.core.task_queue._sanitize_event_value`），平台侧另有
  `_sanitize_payload`：脱敏 `retry_payload` 但**保留业务字段**（prompt/messages/lineage），
  否则重发会还原不出原请求。
- 事件摘要长度上限 `MAX_SUMMARY_LENGTH`（20000）：既能保留完整 prompt 与模型原始输出，
  又不会把整本书正文塞进事件表。

## 7. 文档同步协议

- 新增/改语义 API → 跑 `backend/venv_win/Scripts/python.exe tools/generate_api_surface.py` 重新生成
  `docs/architecture/API_SURFACE.md` 与 `api_surface.json`（勿手改）。
- 模块边界变化 → 更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` 第 5 节；
  数据模型变化 → 第 4 节；阶段性交接 → `docs/devlog/YYYY-MM-DD_topic.md`。

## 8. 写作风格档案

<!-- 来源：openspec/changes/creative-writing-style-profiles，导入日期：2026-09-11 -->

### 8.1 工程约束

1. **T6 层预算 1200 字符，且与项目 Skill 包共用**：强度标签只占两个字、**不额外占行**。把强度说明写长会把风格规则挤出预算，表现为"明明绑定了风格却没注入规则"——这是最容易被误判成 bug 的约束。
2. **注入块必须由纯函数生成**：`build_style_prompt_block` 负责拼装（纯函数便于单测），端与服务不各写一份，避免强度/标签行为漂移。
3. **风格是 T6 的唯一职责**：只能注入表达机制，**不得覆盖 T0-T5 正典、动态状态、章节契约与已批准正文**，也不得把风格内容复制进项目字段。
4. **人机边界必须一一对等**：真人 HTTP 与 Agent 工具共用 `WritingStyleService`。本轮踩坑：Agent 有 `archive` 却缺 `restore`，等于"能归档不能撤销"，实际把归档变成删除——**新增状态流转时 HTTP 与 Agent 工具要同时补**。
5. **`TOOLS` 是函数列表，不是"名字 → 工具"字典**：判断某工具是否注册应比对 `tools/__init__.py` 的 `__all__` 或 `ToolRegistry.get_tool(name)`；写成 `'名字' in TOOLS` 恒为 `False`（本轮据此得出过"注册失败"的错误结论）。新增工具需在 `__init__.py` **三处**同时登记：导入块 / `TOOLS` 列表 / `__all__`（`__all__` 是带引号的字符串写法）。

### 8.2 设计决策

| 决策 | 理由 | 被否决的方案 |
|---|---|---|
| 先内部集成，再经混合模式开放外部 Agent | 内部服务掌握来源访问、存储、校验、激活与运行时注入，一致性与可审计性最好 | **外部 Agent 直连** —— 会绕过溯源/确认/版权控制并造成 schema 漂移 |
| 风格是软约束，只报告偏离 | 偏离多少由人决定，自动改写会破坏人工创作主导权 | 按偏差分数自动回改正文/档案 |
| 提取 / 激活 / 绑定三步分离且每步需确认 | 防止"提取即生效"，保证人始终在环 | 提取后自动激活并绑定 |
| 反模板审查证据驱动 | 机械禁用三段式/排比/短句会误伤正常文学手法 | 黑名单式"三段式即 AI 味" |


## 9. Agent 工作台前端

<!-- 来源：openspec/changes/agent-workbench-ui-redesign，导入日期：2026-09-12 -->

### 9.1 工程约束

1. **窄屏折叠禁用 `:nth-child`**：顶栏控件会随功能增长而插入，序号定位会在新增控件时**静默错位**
   （隐藏的变成新控件、原按钮仍占位导致横向溢出）。改用稳定类名（本项目为 `.agent-rail-optional`）。
   本轮即因插入两个下拉触发该问题。
2. **`tabular-nums` ≠ 等宽字体**：前者只保证数字等宽对齐，后者才是 `font-mono`。若遥测条只写
   `fontVariantNumeric` 而没设等宽字体族，与"等宽数字"的字面要求不符。做法：把等宽字体栈加在
   **容器**上——拉丁字符与数字走 mono，中文标签自动回退 CJK 字体，无需逐个 span 设置。
3. **批量替换 `border` 时按缩进天然分层**：用相同缩进做全量替换，可自动跳过页面外壳等需要保留
   四周框的容器（本轮靠缩进差异正确跳过了 `pageShell`）；但**必须事后枚举确认没漏掉目标**。
4. **JSX 注释不能作为 `&&` 表达式的第二个兄弟节点**：`{cond && (<A/>)}` 里把 `{/* 注释 */}` 与 `<A/>`
   并列会报 `JSX expressions must have one parent element`；注释应放在子元素内部。
5. **内联 `style` 会被样式表的 `!important` 覆盖**：`.agent-workbench` 的媒体查询大量使用 `!important`，
   因此即便元素有内联样式（如 `gridTemplateColumns`），媒体查询里的 `!important` 仍然生效——
   判断响应式行为时不能只看内联样式。
6. **审计"已勾选"任务必须逐条比对字面描述**：本 change 有 3 项勾选与事实不符（#4 横幅位置、
   #5 缺拒绝动作、#14 等宽字体），另有 2 项实现了却没勾（#12 trace 折叠、#17 错误边界）。
   **勾选不等于已实现，反之亦然。**

### 9.2 设计决策

| 决策 | 理由 | 被否决的方案 |
|---|---|---|
| 模型/工作流写回 `AgentProfile`，不进 run 载荷 | change 限定 frontend-only，而 run 载荷本无这些参数；写回配置既真实生效又不碰后端 | 伪造一个"只影响本次"的下拉（无处生效） |
| 缺数据时不伪造 UI 状态 | 会话状态点只渲染可知状态、Token/成本显示 `--`；用默认值冒充会让用户误判 | 用 `updated_at` 反推状态、用 0 代替缺失 |
| 拒绝复用 `cancelAgentRun` 并明确告知后果 | 后端无 step reject；与其不做（规格缺一块）或新增后端（超范围），不如复用现有能力并把差异讲清楚 | 新增 step reject 端点 / 留缺口不实现 |
| 卡片收敛保留四类边框例外 | design §4 明确"仅层级需要时才用卡片"；外壳、表格、选中态、错误隔离都需要边框表达层级或状态 | 一律去边框（表格与选中态失去可读性） |


### 9.3 世界构建

<!-- 来源：openspec/changes/ai-progressive-world-building，导入日期：2026-09-12 -->

1. **复用既有管线的"审阅/写入"半段，只新增"生成"半段**：`WorldExtractionRun` 已有 `domains_json`/`checkpoint_json`/`trace_json`/`diagnostics_json`/`status` 与局部失败语义，`WorldFactCandidate` 已有 `payload_json`/`evidence_json`/`origin`/`status` 与审阅流。新建一套会复制这些机制并制造双份游标语义。
2. **来源性质放在候选级 `origin`，不要放证据上**：放证据上会导致"同一条候选混有多种来源"时无法表达；放 UI 上会导致导出、上下文打包、Agent 返回全部失真。
3. **把"AI 能改什么"的边界前移到响应 schema**：`WorldGenerationSchema` 同时声明 `items` 与 `suggested_*`，模型无法靠"多返回一个字段"偷偷改结构。
4. **同步 vs 异步的判据**：单实体、单次模型调用、`max_tokens=2000`，耗时与既有 `extract` 同量级；`expand_domain` 与未来多域生成需重新评估。
5. **design.md 可能滞后于 tasks.md**：本次审计一度以为 `expand_domain` 未实现（design 的 API 表标"待实现"），实际代码已落地且任务有 `_Done:` 证据。**判断"做没做"以代码与 tasks 的 `_Done:` 为准。**


### 9.4 写作前置检查与 Creative Skill

<!-- 来源：openspec/changes/creative-project-writing-guardrails，导入日期：2026-09-12 -->

1. **Skill 以文件形式存放**：`backend/app/skills/{novel,creative}/<name>/SKILL.md`，`name:` 字段即方法 id。新增方法包沿用同一约定，preflight 才能自动发现。
2. **preflight 与 Agent 共用契约**：不要让 UI 另写一套"能不能点"的判断——否则 Agent 侧解释阻塞原因时会与前端不一致。
3. **⚠ 检索陷阱（本轮实际踩到）**：PowerShell 的 `Select-String -Path <目录> -Include *.py` **不会递归子目录**。审计时先用它搜 `chapter-hook-rhythm` 得到"不存在"，差点误判任务为假勾选；改用 `Get-ChildItem -Recurse | Select-String` 复查才发现文件就在 `backend/app/skills/novel/`。**判断"某物是否存在"必须递归搜索。**
4. **任务注释里可能已有验收证据**：本 change 任务 #9 以日期注释记录了测试数与 Patchright smoke 结果。审计时先读任务下的注释，不要只看标题措辞就判定"无证据"。


### 9.5 制作台与派生状态

<!-- 来源：openspec/changes/story-production-desk，导入日期：2026-09-12 -->

1. **派生状态优先"渲染时计算"而非"落库字段"**：制作台明确拒绝为阶段完成情况新增持久化状态，避免与 `CreativeProject.outline`、`ProjectContent`、任务记录等权威源产生第二份真相。新增任何"完成/进度"类字段前，先问一句"能不能渲染时算出来"。
2. **导航改造不得改变写入路径**：制作台重排的是导航与呈现；后续重构 episode 工作台时**必须**继续复用 `ProjectAssetLink`、内容版本、任务记录与生成日志。
3. **验收必须指向"当前后端"**：任务记录了一次坑——既有的 3002 静态服务器仍代理到旧端口 8000 的后端，验收数据不对；最终用临时本地静态/代理服务器指向 8004 上的当前后端，Patchright 才拿到真实渲染结果。
4. **`/story` 的实现已迁出 `index.tsx`**：现 `index.tsx` 仅 10 行（原 13167 行），制作台相关代码在 `components/StoryWorkspaceShell.tsx`、`components/outline.tsx`、`utils.ts`。查找 `/story` 实现不要再只看 `index.tsx`。


### 9.6 数据库迁移

<!-- 来源：openspec/changes/database-migration-convergence，导入日期：2026-09-12 -->

1. **⚠ `alembic_version.version_num` 默认只有 `VARCHAR(32)`**，存不下长 revision id（本仓库 `003_add_image_prompt_reference_library` 即超长），首次演练因此在 revision 003 完成前就失败。修法：在 revision 003 的**第一个操作**把该字段扩到 `VARCHAR(128)`——**必须早于** Alembic 写入自己的 revision id。
2. **⚠ 只由运行时 `create_all()` 建出的表，全新库会缺**：`project_publish_records` 曾在 SQLModel 中存在但 revision 001–007 都没有，只有运行时 `create_all()` 提供。判断"迁移链是否完整"**不能只看代码能跑通，要看全新库能否从 001 升到 head**（用一次性演练库验证）。
3. **Alembic `env.py` 必须导入完整模型包**：`import app.db.models` 后再赋 `SQLModel.metadata`，`--autogenerate` 才能看到全部表而非手工挑选的子集。已有回归测试守护。
4. **只读诊断优先**：`tools/check_migration_state.py` 只读 `alembic_version`、报本地 head、对密码脱敏，**不**调用 upgrade/stamp/create_all/DDL。结果非 current 是"备份与演练的依据"，不是"可以改远程库的许可"。
5. **元数据漂移数字要谨慎解读**：全量比较报 177 处差异的同时，revision 003–007 引入的十张表其实都已存在且与代码一致。大差异**不等于**远程 schema 未收敛——其中大量是已废弃 legacy 表与历史 default/nullable 漂移。
6. **禁止 `stamp head` 假收敛**：`stamp` 会掩盖真实缺表。远程库只能显式 `alembic upgrade head`，不删表、不重置、不重写数据。


### 9.7 创作项目动态状态

<!-- 来源：openspec/changes/creative-project-dynamic-state，导入日期：2026-09-12 -->

1. **状态更新走"LLM 输出字段"而非工具调用**：`prose_review` 的 JSON 输出新增 `state_changes`（与 `continuity_candidates` 并列），由 `ChapterAftermathPipeline` 的 `state` 阶段确定性读取并落账。**正文 prompt 零改动、新增零工具**——避免创作主链路塞入工具调用导致的延迟与不确定性。
2. **纯服务优先**：`StateLedger` 不依赖 HTTP 与请求上下文，用 fake session 即可单测折叠/去重/回滚。新增"计算型"能力时先问能否做成纯服务。
3. **注入必须分层且预算有界**：`dynamic_state` 只全量注入 `world` 与**当前章出场的角色**；未出场角色的长尾交给既有 T5 语义召回，不做全量塞入。
4. **无新 HTTP 路由时不改 API surface**：判断是否需要更新 API surface 的依据是**路由是否变化**，不是功能是否变化。


### 9.8 创作项目叙事运行时

<!-- 来源：openspec/changes/creative-project-narrative-runtime，导入日期：2026-09-12 -->

1. **T0 永不静默截断**：超出时**必须显式报 `context_overflow`**，而不是悄悄丢掉一部分锁定正典。T1–T6 走预算制，并**记录被纳入/排除的源 ID 与原因**。
2. **异步生图不能"让正文运行成功"**：图像生成是**外部生产任务**，只有**任务真正完成且 Asset Hub 谱系回写已校验**后，才算生产运行成功。（2026-09-12 实测补充：`generate-storyboard` 只产出文字分镜草稿、**不产生生图任务**，该闸门在实测中未被触发。）
3. **熔断器触发条件**：反复供应商失败、上下文溢出、结构化输出非法、预算超限、质量底线持续不达标；**恢复必须显式用户动作**，不自动重试。


### 9.9 Agent 工作台信息架构约束

<!-- 来源：openspec/changes/agent-center-conversation-workbench-redesign，导入日期：2026-09-12 -->

1. **三条产品约束**（写入架构约束）：① **低门槛**——降低普通人操作门槛；② **结果可视**——直观呈现过程与产物；③ **脚本优先**——确定性操作交给脚本与服务，减少模型调用与 Token 消耗。YLCraft 的价值不是"堆更多配置"。
2. **Agent 页面的 Markdown 是手写解析器，不是第三方库**：`parseInlineMarkdown` + `parseSimpleMarkdown`（`pages/agent/index.tsx:357-395`）自己产出 `MarkdownBlock`（paragraph / heading / list / quote / table）。排查 Agent 消息渲染问题时**不要去找 `react-markdown`**。


### 9.10 小说来源与世界提取

<!-- 来源：openspec/changes/novel-source-world-project，导入日期：2026-09-12 -->

1. **序列化大纲也必须满足"逐字证据"**：把项目大纲转成来源文本时，每个字段要带 `【节】` 标记，使 AI 引用的引文能逐字落在该文本上从而通过证据校验（与小说来源同一套规则）。
2. **核对实现必须用递归搜索**：本项目曾因 `Select-String` 只给目录（不递归子目录）而漏掉子目录实现，得出"没实现"的错误结论。
3. **内置域字段只可追加、不可删除**：`world_domain_definitions` 允许覆盖标签/提示词、追加字段、禁用模块、添加自定义模块，但内置字段**禁止删除**——否则既有 `attributes_json` 会解析失败。AI 建议的模块落库为 `ai_suggested`，**默认不参与提取**，须转 `custom` 并启用。
4. **`npm run smoke:pages` 是源码文本扫描，不是页面/浏览器验证**：它只做 `readFileSync` + `includes()` 找 marker，**既不挂载页面也不启动浏览器**，通过**不代表**页面能运行。真实 UI 验证须用 `patchright`（后端 venv 已装）+ Chromium 驱动真实浏览器。


### 9.11 创作项目闭环

<!-- 来源：openspec/changes/creative-project-closed-loop，导入日期：2026-09-12 -->

1. **阶段模板体系要兼容历史模板**：扩展 `platform_templates` 增加 `template_scope` / `template_stage` / `description` / `system_template` / `variables`，使历史多平台图片模板继续可用，同时创作项目的系统/用户提示词可在模板管理 UI 编辑。**内置模板是兜底**，用户覆盖优先。
2. **生图回写项目谱系必须带齐字段**：`POST /images/generate` 需带 `project_id` + `content_id` + `source_type`，且 `source_index` / `chapter_number` **须为字符串**（传整数会 422）；只调 `/images/generate` 而不带这些字段**不会**产生项目 `derived_from` 谱系——容易误读为"生图不写谱系"。
3. **生成单元独立存储是硬要求**：把多阶段产出塞进一个 JSON blob 会导致无法单独重生成/版本化/检索，是本项目明确否决的做法。
4. **实验模块不得混入主流程**：新增能力若尚未接入项目闭环，应在导航中标注为实验，而不是让用户以为已可用。

### 9.12 相关设计决策

| 决策 | 理由 | 被否决的方案 |
|---|---|---|
| **新建表（Path A）而非扩展 `stories`** | `Story` 命名与字段对小说/漫画/短剧/画布过窄；新表更清晰且不破坏既有 Story Maker | 在 `stories` 上加 JSON 字段（Path B） |
| **首版只做最小闭环** | 只覆盖大纲、章节计划、小说导入与生图交接 | 一次性交付全部阶段与画布 |
| **画布是项目组合面** | 承载"项目 → 产物 → 素材"的编排 | 做成独立功能页 |
| **LLM JSON 靠工程兜底** | Pydantic 校验 + 一次修复 + 原始日志 + 版本化 | 仅靠提示词保证 JSON 正确 |


### 9.13 提示词参考库

<!-- 来源：openspec/changes/image-prompt-reference-library，导入日期：2026-09-12 -->

1. **大数据量标签筛选走 PostgreSQL JSONB 聚合**：避免 Python 侧冷扫描；**分面建议必须基于全量过滤结果集而非当前页**，否则分面会随翻页漂移。
2. **非法枚举值不应被静默忽略**：`model_group=nanobanana`（小写、非规范值）当前返回**全量**结果而非空集或 400——这种"过滤已生效"的错觉会污染数据判断。新增过滤参数时应让非法值返回空集或校验错误。
3. **测试选择器会过时，引用前必须复核源码**：某任务记录的画布选择器 `[data-canvas-open-node]` 在当前源码已不存在，实际是 `data-canvas-node-id` / `data-canvas-node-title` / `data-canvas-node-type`。**照抄过时选择器会让 smoke 假失败或假通过。**
4. **缓存媒体本地优先**：有本地缓存时优先本地 URL，远端 URL 仅兜底，避免上游失效导致图库大面积空白。
5. **`npm run smoke:pages` 不是浏览器验证**：它只做源码 marker 扫描；真实 UI 验证须用 `patchright` + Chromium。

### 9.14 相关设计决策

| 决策 | 理由 | 被否决的方案 |
|---|---|---|
| **提示词库与 `PlatformTemplate` 分离** | 平台模板是发布格式模板，提示词库是创作素材；混用会污染两者语义 | 复用 `PlatformTemplate` 存提示词 |
| **提示词引用不进素材库** | 素材库是**项目产出**的记忆；提示词是**输入素材**，自动入库会淹没产出 | 插入引用即入 Asset Hub |
| **同步默认本地优先** | 远端仓库不稳定且易限流；本地已有数据应可直接用 | 每次刷新都打远端 |


### 9.17 图转 3D 工作台（自动化与验证的坑）

<!-- 来源：openspec/changes/image-to-3d-workspace，导入日期：2026-09-13 -->

1. **`/model-3d/history` 会过滤掉 `pending` 任务**。用它判断"新任务是否创建"会得出错误结论（曾出现接口显示 5 条、库里实际 6 条）。核对提交是否成功应查任务表或 `GET /model-3d/tasks/{task_id}`。
2. **生成表单默认折叠**——须先点「创建模型」展开右侧面板，否则定位不到控件。
3. **提交按钮文案是「生成 3D 模型」**，不是「生成」。
4. **Ant Design `message.warning` 约 3 秒自动消失**——自动化验证等待过久会看不到拦截提示，误判为"点了没反应"。
5. **真实生成会扣供应商额度**（Hunyuan 3D 回执 `ResultCreditConsumed`，实例为 20 点）。**任何触发真实生成的验证必须先向用户确认费用。**

**判断是否绑骨**：解包 GLB 的 JSON chunk 看 `skins`（骨架绑定）与 `animations`；两者皆为 0 即静态网格。


### 9.18 角色册实现约束

<!-- 来源：openspec/changes/character-management-redesign，导入日期：2026-09-13 -->

1. **Bible 分节字段类型不统一**：`identity` / `ability` / `behavior` / `motivation` / `speech` / `voice` 是对象，但 **`arc` 既可能是字符串也可能是对象**（实测 11/20 填充且类型混杂）。判空与渲染必须两种都处理，否则会把已填的 `arc` 当成空。
2. **`identity` 对象的键不固定**：取摘要要按 `summary → logline → affiliation/organization → personality → background` 优先级链兜底。
3. **窄栏视觉弱化必须给选中态留出口**：未完善角色整体降不透明度（实测用 0.62）会被误读为"不可点"，**hover 与选中态必须恢复满不透明度**。验收断言若只取第一个 `.is-thin` 元素，会拿到当前选中项（opacity=1）而误判"弱化没生效"——**需排除选中态**。
4. **完善度指示器做成细条放名字行右侧**（3px），摘要做第三行单行省略——不在窄栏里额外增加行高压力。


### 9.19 视频生成实现约束

<!-- 来源：openspec/changes/ai-video-workspace，导入日期：2026-09-13 -->

1. **视频的项目 `role` 是 `output`，不是 `generated`**。视频完成后 `GET /creative-projects/{id}/assets` 返回
   `role=output` + `relation=derived_from`；生图路径才是 `role=generated`。**按 `generated` 断言会误判"没有谱系"**。
2. **WebSocket 协议必须跟随页面协议**。`frontend/src/hooks/useWebSocket.ts` 曾硬编码 `wss://`，
   而开发环境页面与后端都是明文 HTTP，握手必然失败（`ERR_SSL_PROTOCOL_ERROR`），使**实时任务进度在本地静默失效**
   （受影响：任务中心 `/tasks`、`/video-gen`、Live2D）。正确写法见同库 `api/comfyui.ts` 与 `pages/accounts/index.tsx`：
   `const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'`。
3. **图生视频需要公网可达的首帧**（Agnes `image_requires_public_url=true`）；本地验证优先用**文生视频**。


### 9.20 外部研究对照：Agent Harness 与团队记忆（2026）

<!-- 来源：arXiv 2608.25512《A Programming Paradigm for Spatiotemporal Composability》（北大 × DeepSeek-AI，92 页，cs.PL/cs.SE）；《任何错误只犯一次：TencentDB Agent Memory 的团队记忆实践》（https://mp.weixin.qq.com/s/-ghlUNmB8HvzX9cFYXlDKg）；《16 个超火的 DeepSeek Harness 插件》（https://mp.weixin.qq.com/s/gbsL7qsPD7wd6iI0DGojng）。PDF 存于 docs/papers/2608.25512-spatiotemporal-composability.pdf。导入日期：2026-09-13。 -->

> **性质声明**：本节是**外部对照，不是本项目已采纳的约束**。列出的是"别人怎么做"与"我们的差距"，
> 是否采纳需单独决策（可能各开 change）。引用外部材料时请回原文核对，勿把转述当结论。

#### 9.20.1 论文的两个正交维度（原文术语）

DeepSeek × 北大论文把"动态组合"拆成：

| 维度 | 原文定义 | 缺了会怎样（原文） |
|---|---|---|
| **时间可组合性** | "the ability to **completely revert a component's side effects upon removal**" | "each self-modification forces a full restart that discards all process-local accumulated state"；"a faulty self-modification can disable the very process needed to recover" |
| **空间可组合性** | "the ability to **declare and reactively manage inter-component dependencies**" | "each module must itself detect and adapt to changes in the modules it depends on... a naive code-replacement strategy may silently break dependents or **introduce circular dependencies that surface only at reload time**" |

核心机制（原文贡献 1–5）：**revertible effects**（每次上下文变换携带运行时持有的**显式逆操作**）、
**reactive coeffects**（组件声明 specification，上下文变化被分类为 **activating / deactivating / neutral** 以驱动启停）、
**context paradigm**（两者统一为单一 context 类型，中介出 **observational equivalence**）、
**calculus of dynamic composition**（元理论把可组合性从单组件传递到整个交错系统）、
**Cordis**（实现：effect tracking + coeffect resolution + **declarative component loader with configuration reconciliation and hot module replacement**）。

论文 §1.2.3 的判断：进程/容器级的粗粒度替代**不能表达同一地址空间内的依赖**，且重启代价是"丢掉全部进程内累积状态（缓存、连接、部分计算）"。

#### 9.20.2 团队记忆的五步路由分层（TencentDB Agent Memory）

原文的装配顺序**不是对全库做一次相似度搜索，而是逐层缩小**：

1. **身份与作用域层** —— **没有权限的资产不进入候选池，而不是召回后再删除**
2. **固定绑定层** —— 角色规则/任务约束/指定 Wiki/必需 Skill **直接进入装配范围**；"它们表达的是组织事实，不应被一次相似度排序覆盖"
3. **浮动召回层** —— 权限范围内补充历史记忆与候选
4. **相关性融合层** —— 错误码/文件名/符号走 **BM25**，意图/故障模式走**向量**，两路 **RRF 融合**
5. **上下文装配层** —— 按角色/优先级/绑定/版本/**Token 预算**生成 Memory Pack；**任务期间可锁定资产版本**

配套：**内容分层 L0→L3**（原始对话 → 原子事实/约束/决定 → 场景记忆块 → 稳定画像），
"**高层负责减少阅读量，低层负责防止抽象在多轮总结后失真**"；
**渐进式暴露**（Prompt 告诉"有什么"，工具调用在需要时取细节）；
原则句：**"完整属于资产池，相关属于当前任务"**；
资产形成四步：证据切分 → 候选抽取 → **作用域绑定**（Owner/Team/Repo/Branch/Path/Version/Time/ACL/证据）→ **验证后升级**。

**实证（原文数据）**：2600 Session → 5081 Task；48114 候选 Pair → 22361 canonical Relation；
但**三类强关系仅 231 条**，其余 22130 条降为 Shadow（**只参与召回，不驱动执行**）。
洞察：**"关联不等于复用，复用也不等于可以直接执行。"**
卡点分布：逻辑返工 **1350** ≫ 缺少上下文 269 → 所以记忆不能只"找资料"，还要保存**决策理由、失败路径、适用条件、验证方式**。
效果：SWE-bench 相关 Case 完成率 **60%→80%**；Top50 超长难任务通过率 17%→20%、成本降 19%
（**原文自己限定**："不等于部署 Memory 后所有任务都会提升 20 个百分点"）。

#### 9.20.3 对照本项目的**缺口清单**（待决策，非已采纳）

已做对（与上述做法同源）：T0 锁定正典**不被相似度覆盖且永不静默截断**；**待决候选永不进入 T0–T5**（≈ Shadow 不驱动执行）；
Context Pack **记录纳入/排除的源 ID 与原因**（≈ 可溯源）；存储用**项目根相对路径**（≈ 框架中立）。

**尚缺**：

| # | 缺口 | 外部做法 |
|---|---|---|
| 1 | 混合检索**没有融合算法** | BM25 + 向量两路 **RRF 融合** |
| 2 | 只有**按用途**分层的 T0–T6，缺**按提炼层级**的分层 | **L0 原始证据 → L1 原子 → L2 场景 → L3 画像**（与 T 层正交） |
| 3 | 资产生命周期字段不全（有 `superseded`） | 补 **`valid_from` / `valid_to` / 最后验证时间 / 代码版本** |
| 4 | **人的负反馈不改变后续路由** | "错误召回不能只依赖下一次模型自己判断"——负反馈必须**降权/撤回并影响相似资产的触发规则** |
| 5 | 无**固定绑定 vs 浮动召回**的显式二分（T0 是特例） | 固定绑定层与浮动召回层**分开建模**，固定资产不被排序覆盖 |
| 6 | 无"可逆效应/逆操作栈"（`AgentScope` 只是作用域隔离） | 论文的 **revertible effects**：变换携带显式 inverse |

**若要做"Agent 自我修改工具"（自进化），第 6 条是前置**——否则每次改动只能重启，丢掉全部累积状态。


### 9.21 Agent 运行时审计方法与约束

<!-- 来源：openspec/changes/agent-supervisor-subagent-runtime，导入日期：2026-09-13 -->

1. **审计文案要防"反向失真"**：过时描述**不只会高估**，也可能**低报**（本项目实测：文档称"Writer Room 仍是单模型推演""Coordinator 尚未迁移"，而两条均已不成立）。审计必须**双向**核对，不能只查"是否夸大"。
2. **首屏空态会让 UI 断言误报**：`/agent`、`/story` 在无会话/未选项目时正文仅约 1k 字符，委派入口与团队模式控件**均不可见**。断言必须先驱动到"有会话 / 进入写作室"，否则把"没进入状态"误判成"功能缺失"。
3. **默认折叠的内容不在 `inner_text` 里**：运行执行过程位于默认折叠的 `<details>` 中；须查 DOM（`document.body.innerHTML`）或先置 `details.open = true`。
4. **统计 Python 测试函数必须匹配 `^(async )?def`**：`^def` **匹配不到 `async def`**；本项目曾因此误判"parent resume / confirmation 无测试"（实际都在 `test_agent_center.py`）。
5. **`AgentService(session)` 只需一个 session**，内部自建 `ThreadManager`/`MemoryManager`/`AgentProfileManager` 等；测试可直接构造，无需手工拼装管理器。


### 9.22 声明式团队组合与平面隔离

<!-- 来源：openspec/changes/agent-team-composition，导入日期：2026-09-13 -->

1. **`AgentScope` 需要一个"安装既有作用域"的入口**：`enter(host, agent)` 只能装**新建**的；调用方常需要先 `child()` 派生（继承 host 与团队上下文、隔离 agent 平面）**再安装**，故补 `AgentScope.enter_scope(scope)`，退出与异常路径都恢复上一层。
2. **隔离要靠结构保证，而不是"恰好各自 new 了实例"的约定**：接线 per-session 状态到作用域前复核发现，`AgentService` 的状态**本就是实例级**、`services/agent/` 下**无模块级可变态**——即"角色共享可变实例"的风险**当时并不存在**。价值在于把隔离从约定升级为结构保证。**结论：动手前先核实缺陷是否真存在，别修一个想象出来的问题。**
3. **同一形状的定义只能有一份**：`capability_diff` 与运行授权溯源原本会各写一份角色能力形状，提取公共 `role_capabilities(role)` 后共用，避免漂移；顺带让此前**在生产代码里零调用**的 `capability_diff` 真正被用到。
4. **"零调用"的工具函数是警报**：某函数只有测试在调、生产无调用，说明其设计意图（如"路由经审批"）很可能从未接线。定位缺口时可据此快速判断。
5. **平台级 API Key 的开关语义**：`YLCRAFT_EXTERNAL_API_REQUIRE_KEY` **关闭 ≠ 不校验**——不强制携带，但**携带即必须有效**（无效 Key 仍 401）。


### 9.23 内容包与媒体生成

1. **`Form.List` 里的原生 `<button>` 必须显式 `type="button"`**：HTML 默认 `type=submit`，放进 antd `<Form>` 后一点就会**提交整个表单**（表现为"顺手保存并关闭弹窗"）。本项目已在 `GeneratedMediaThumb` 三处按钮踩过；antd `<Button>` 默认 `htmlType="button"` 无此问题，风险只来自原生 `<button>`。
2. **`imageContextKey` 会补齐 `chapterNumber`**：写入端用 `context.chapterNumber ?? activeChapterNumber` 生成键，读取端若漏掉该字段就会得到**另一个键**——表现为"生成成功却在界面上看不到"。跨组件读写同一份 `inlineImages` 时必须用同一组键输入。
3. **单条生成与批量生成的结果写入位置必须一致**：批量路径写回条目表单（`items[i].image_url`/`asset_ids`/`status`），单条路径原先只写页面级 `inlineImages`。已让单条也写回表单（与批量一致，保存时能随包落库）；写回时**只在新地址非空时才覆盖** `image_url`，否则异步分支只回 `assetId` 会把已有图抹掉。
4. **编辑器字段值在 `input`/`textarea` 里，`inner_text` 读不到**：用浏览器断言表单类界面时，必须读控件 `value`；用 `inner_text` 会误判为"字段没渲染"。
5. **缩略图等异步渲染元素的计数会抖动**：`img[src*=...]` 的计数在重渲染瞬间可能少一个，**不能据此判定数据丢失**——以数据库/接口为准再下结论。
6. **`tsconfig` 关闭了 `noUnusedLocals`，`tsc` 不会报死导入**：删代码后要另行按"标识符是否只出现在导入行"扫一遍死导入。
7. **`frontend/` 没有 ESLint 配置**（`package.json` 也未声明 eslint 依赖）：`npm run lint` 脚本存在但跑不起来，**在未改动代码上同样失败**，属既有工具链缺口。
8. **免费生图后端 Agnes**：连接器 `agnes-image-21-flash`（provider `agnes`，模型 `agnes-image-2.1-flash`，支持文生图+图生图），尺寸取值为 `1K/2K/3K/4K`；可用于不消耗额度的真实生图验证（约 10–15 秒/张）。
9. **`context-index.yaml` 的引号标量里必须用中文引号「」**：`summary:` 与 `triggers:` 项都是双引号包裹的 YAML 标量，**内层再出现 ASCII 双引号会提前闭合字符串**，整个文件无法解析。本项目已犯 **3 次**（2026-09-13 一次、2026-09-14 两次），且两次都是"注入完知识、以为成功了"之后才发现。**改完索引必须立刻跑一次 `yaml.safe_load` 复验**，不要等到提交前才发现。
