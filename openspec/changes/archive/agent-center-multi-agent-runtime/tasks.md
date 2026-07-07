## M0. Stabilize Current Agent Loop

- [x] M0.1 修复 JSON fallback 工具循环，避免向不支持原生 function calling 的模型发送裸 `role=tool` 消息。
- [x] M0.2 `/agent` 页面展示自动工具循环、运行轨迹和工具摘要。
- [x] M0.3 工具结果默认摘要展示，原始 JSON 折叠查看。
- [x] M0.4 在页面明确解释“工具未授权”的含义和处理方式。
- [x] M0.5 增加一个可手动触发的“工具调用测试”入口，验证当前智能体是否能调用指定工具。

## M1. Durable Runtime Foundation

- [x] M1.1 增加 `AgentRun` 模型：`id`、`session_id`、`profile_id`、`parent_run_id`、`status`、`objective`、`context_json`、`result_json`、`error`、`started_at`、`finished_at`。
- [x] M1.2 增加 `AgentRunStep` 模型：`run_id`、`step_type`、`agent_profile_id`、`status`、`input_json`、`output_json`、`summary`、`error`、`duration_ms`、`order_index`。
- [x] M1.3 新增 run API：创建、详情、列表、取消、继续、重试失败步骤。
- [x] M1.4 将 `AgentService.chat` 内部拆成 `intake -> context_pack -> plan -> tool_select -> execute -> observe -> decide -> final`。
- [x] M1.5 每次 LLM 请求、工具调用、工具观察和最终回答都写入 run step。
- [x] M1.6 工具调用结果关联业务对象：project、chapter、character、asset、task。
- [x] M1.7 页面增加 run 时间线，支持按 step 状态筛选。

## M2. Tool Calling Upgrade

- [x] M2.1 为 OpenAI SDK LLM 后端接入原生 `tools/tool_calls`，正确保存 assistant tool_call message 和 tool result message。
- [x] M2.2 为 Generic HTTP LLM 后端增加 tool calling 配置：工具字段路径、arguments 字段路径、结束条件字段。
- [x] M2.3 ToolRegistry 增加风险等级：read、write、delete、external、costly，并为主要工具补齐输入/输出说明。
- [x] M2.4 高风险工具执行前生成 pending step，等待用户确认。
- [x] M2.5 工具结果统一三层结构：summary、raw_json、linked_objects。
- [x] M2.6 增加工具参数校验错误的可读提示。

## M3. Memory And Context

- [x] M3.1 页面展示当前注入的 session context、project context、default context、memory snippets。
- [x] M3.2 会话结束后抽取用户偏好和项目规则，写入 `agent_memories`，支持用户确认后保存。
- [x] M3.3 为创作项目生成 context pack：项目圣经、角色卡、章节状态、素材引用、最近任务。
- [x] M3.4 AgentProfile 支持绑定默认项目、默认工作流、默认 Skill。
- [x] M3.5 Skill 模板第一批：小说补全、角色视觉卡补全、分镜生成、参考图匹配、漫画图片提示词生成。

## M4. Creative Multi-Agent Team

- [x] M4.1 AgentProfile 增加 `role_type`：orchestrator、writer、character_designer、storyboard_director、asset_curator、reviewer。
- [x] M4.2 新增 delegated subtask：父 run 可以创建子 run，并记录委派人、执行人、输入和输出。
- [x] M4.3 预置创作团队：
  - 总控导演：拆任务和验收。
  - 小说作者：正文、人味改写、章节续写。
  - 角色设定师：角色卡、视觉卡、立绘提示词。
  - 分镜导演：脚本、镜头、漫画页、图片提示词。
  - 素材管家：素材检索、参考图集合、资产关联。
  - 质检编辑：连续性、设定一致性、缺失项。
- [x] M4.4 创作项目页面新增“一键推进”入口：选择目标后创建 orchestrator run。
- [x] M4.5 子 Agent 输出必须回写父 run，并在 UI 显示委派链。

## M5. Workbench UI

- [x] M5.1 工作台增加 Agent roster：显示可用智能体、角色类型、模型、授权工具数。
- [x] M5.2 中间增加 Run Timeline：计划、工具、观察、回答、失败步骤。
- [x] M5.3 右侧增加 Context Panel：当前项目、记忆、默认上下文、产物引用。
- [x] M5.4 Settings Drawer 拆成 Profile、Model、Tools、Memory、Default Context 标签。
- [x] M5.5 工具抽屉按分类、授权、风险和输出类型展示，工具卡片显示输入/输出规范；Tool result 卡片保留摘要和原始 JSON。
- [x] M5.6 增加失败态设计：错误摘要、原始错误、建议下一步、重试按钮。

## M6. Observability And Safety

- [x] M6.1 Agent run 与现有任务日志/请求日志打通，能从 run 反查 LLM 请求和工具调用。
- [x] M6.2 每个 run 支持导出 Markdown：目标、计划、步骤、产物、错误。
- [x] M6.3 对 costly 工具记录花费或预估花费。
- [x] M6.4 对 delete/external/write/costly 工具默认要求确认。
- [x] M6.5 增加权限拦截测试和 UI 提示测试。

## M7. Validation

- [x] M7.1 增加 fallback 工具结果不使用裸 `role=tool` 的回归测试。
- [x] M7.2 增加 run step 持久化测试。
- [x] M7.3 增加 native tool calling 协议测试。
- [x] M7.4 增加 delegated subtask 测试。
- [x] M7.5 增加前端构建和关键页面 smoke test。
- [x] M7.6 更新用户文档：如何创建智能体、如何授权工具、如何查看运行轨迹。

## M8. Tool Coverage Extensions

- [x] M8.1 接入 AI 生图工具：列出后端、预览请求、确认后生成图片、轮询异步任务，并补齐输入/输出规范、风险等级和成本提示。
- [x] M8.2 接入 AI 视频工具：列出后端、预览请求、确认后生成视频、轮询异步任务，并补齐输入/输出规范、风险等级和成本提示。
- [x] M8.3 完善创作项目工具契约：修正工具说明乱码，补充完整内容读取和内容写回工具，使智能体可按项目/章节读取、改写并保存产物。
- [x] M8.4 接入项目参考图闭环工具：列出项目素材关联、挂载素材到项目/内容、为脚本/分镜/漫画页匹配 reference_asset_ids，并补齐默认智能体授权。
- [x] M8.5 接入项目生成日志工具：支持智能体按项目/阶段/状态/场景查询日志摘要，并读取单条日志的完整 prompt、request、raw_response、normalized 和 validation_error。
- [x] M8.6 完善素材库工具契约：修正工具说明乱码，统一搜索/详情/文件引用/标签/删除的输入输出规范，并让搜索默认过滤已删除素材。
- [x] M8.7 完善字幕和 BGM 工具契约：修正工具说明乱码，统一字幕提取/样式/烧录与 BGM 搜索/混音/上传的输入输出规范。
- [x] M8.8 完善剪辑和爆款拆解工具契约：修正工具说明乱码，统一异步剪辑任务、任务轮询、外部爆款分析和仿写脚本生成的输入输出规范与风险提示。
- [x] M8.9 接入 Prompt 模板工具：支持智能体列出、读取、预览渲染和确认后更新平台/创作项目模板，使大纲、正文、脚本、分镜和生图提示词模板可以纳入工具闭环。
- [x] M8.10 接入 AI 配置只读工具：支持智能体列出和读取非敏感模型连接器配置，明确默认模型、SDK/HTTP 模式、参考图能力、尺寸和解析参数，避免模型选择依赖猜测。
- [x] M8.11 接入任务中心工具：支持智能体列出、读取、取消和删除任务记录，统一排查下载、生图、视频、字幕、剪辑和创作任务的进度、事件、结果和失败原因。
- [x] M8.12 接入小说库工具：支持智能体读取本地书源和小说书架，并在用户确认后访问外部书源搜索小说、读取目录和预览章节正文，作为短剧/漫画/小说创作项目上游素材。
- [x] M8.13 接入下载解析工具：支持智能体确认后解析外部视频/文章链接、创建后台下载任务并轮询下载进度，作为素材库和创作项目的上游采集入口。
- [x] M8.14 接入公众号工具：支持智能体读取公众号连接摘要，并在确认后搜索公众号、拉取文章列表和下载单篇文章，作为素材库和创作项目的内容采集入口。
- [x] M8.15 接入 TTS 和电子书工具：支持智能体预览/确认后生成旁白音频，以及从本地 Markdown/HTML 文件夹生成 EPUB 并查询任务状态。
- [x] M8.16 接入语义检索和素材血缘工具：支持智能体按语义/相似度查找参考素材，读取素材上下游血缘、统计关系，并在确认后创建素材血缘关系。
- [x] M8.17 接入本地阅读和导出质检工具：支持智能体浏览/预览本地下载文档、确认后删除本地文档，以及读取数据集统计、导出素材 ZIP、计算质量分、查找并合并重复素材。
- [x] M8.18 接入平台采集工具：支持智能体读取平台连接摘要，确认后搜索外部平台内容、获取内容详情/无水印资源，并将采集结果导入素材库。

## M9. Polish & Production Hardening

- [x] M9.1 术语统一：全系统将"步数上限/最大工具步数"替换为"迭代预算（轮）"，前端表单 label/tooltip/Alert、后端 API field description、Profile 配置同步更新。
- [x] M9.2 预算含义可解释：Form.Item 增加 tooltip 解释"每轮计划→工具→观察→继续执行"的循环含义，Alert 描述更新为完整说明，强调预算是防跑偏安全阈值而非能力上限。
- [x] M9.3 工作台风格优化：降低卡片感（boxShadow=none，borderRadius 从 12 降至 4-6），主面板和侧边栏统一使用 flat background（bgPage 替代 bgCard），消息气泡减少阴影和圆角。
- [x] M9.4 自动循环迭代跟踪：`_tool_loop_phase` 显式记录 iteration/budget/remaining 状态，预算耗尽时自动注入总结提示并触发最终回答，每轮工具执行前输出 debug 日志。
- [x] M9.5 上下文增强注入：`_context_pack_phase` 提取项目标题/阶段/角色/缺口摘要并注入 `context_summary`，`_call_llm` 优先于 memory 将项目上下文拼入 system prompt。
- [x] M9.6 工具 Schema 类型推断改进：`register_tool` 的 `_annotation_to_json_schema` 正确处理 `list[X]`（生成 `items` 子 schema）、`dict`（type=object）、`Optional[T]` 和 Union 类型，提升 LLM 工具调用参数准确性。
- [x] M9.7 后端 API default max_steps 从 4 提升到 8，并添加 Field description 说明其语义。
- [x] M9.8 前端构建通过验证：npm run build 通过（既有 chunk 警告不影响），smoke:pages 覆盖 /agent /story /characters /assets /settings。
- [x] M9.9 测试保持：50 passed，python -m pytest tests/test_agent_center.py 全绿。

## M10. Phase 5 Multi-Agent Coordination

- [x] M10.1 新增 `role-actor` 内置 profile：角色演员，系统提示要求读取角色卡后以角色身份输出情绪状态/目标动机/对话候选/行动意图，max_steps=8。
- [x] M10.2 新增 `divine-director` 内置 profile：天意总导演，从上帝视角产出行程指令（冲突设计/节奏地图/世界事件/角色调度/钩子建议），max_steps=10。
- [x] M10.3 新增 `story-editor` 内置 profile：编辑润色师，五维度检查（逻辑/一致性/节奏/钩子/可画面化）+ 逐条修改建议 + 全局 A/B/C 评分，max_steps=10。
- [x] M10.4 前端 ROLE_TYPE_LABELS 新增 director/role_actor/editor 三个中文标签。
- [x] M10.5 实现 `MultiAgentCoordinator` 服务：四阶段流水线——天意导演→角色演员（每角色）→编辑润色→创作导演合成。每个 agent 独立调用 AgentService.chat()，前序输出注入后续 context。
- [x] M10.6 新增 API 端点 `POST /agent/multi-agent/scene-simulation`：接收 project_id、scene_context、characters_of_interest、iteration_budget_per_agent，返回 pipeline_steps + candidate_version_id。
- [x] M10.7 候选版本存储：`_store_candidate()` 输出 structured pipeline log，标记为候选而非自动最终内容。完整存储待 creative project content versioning API 支持 candidate_flag 后激活。
- [x] M10.8 更新 creative-project-optimization-roadmap tasks.md：Phase 5 全部 5 个任务标记为完成。
- [x] M10.9 更新 docs/agent/agent-center.md：修复旧术语"最大工具步数"→ "迭代预算"。
- [x] M10.10 验证：50 passed 测试全绿，0 linter 错误。

## M11. DeerFlow & Hermes Runtime Hardening

借鉴 DeerFlow 2.0 和 Hermes Agent 的成熟架构模式，加固 Agent Center 运行时核心。

### M11.1 上下文压缩 (ContextCompressor)

- [x] M11.1.1 实现 `ContextCompressor` 类：sentinel 预检查 + token 阈值触发 + 可插拔压缩策略。
- [x] M11.1.2 实现 `estimate_tokens()` 快速估算函数：中文字符 ×1.5 + ASCII 字符 ×0.25，避免引入 tiktoken 依赖。
- [x] M11.1.3 实现 `token_budget_check()` sentinel：每次 `_call_llm()` 前快速检查 tokens，超出阈值时触发压缩。
- [x] M11.1.4 压缩策略：总结最旧消息（结构摘要：角色分布、话题关键词），保留最近 8 条消息完整，注入摘要为 system 消息。
- [x] M11.1.5 可配置参数：DEFAULT_TOKEN_THRESHOLD=12000、DEFAULT_KEEP_LAST_MESSAGES=8、MAX_SUMMARY_CHARS=3500、MIN_RESPONSE_BUDGET=2048。

参考来源：
- DeerFlow SummarizationMiddleware：token 阈值触发 + retain-N-last 策略（默认 keep 10、阈值 15564）
- Hermes sentinel：每次 LLM 调用前做快速预检查，只在必要时触发压缩

### M11.2 循环检测 (LoopDetector)

- [x] M11.2.1 实现 `LoopDetector` 类：滑动窗口哈希检测 + 连续同工具计数器双重策略。
- [x] M11.2.2 哈希生成：SHA-256 on `(tool_name, canonical_JSON_args)`，取前 16 位 hex。
- [x] M11.2.3 检测逻辑：10 轮窗口内同一哈希出现 3 次告警循环模式；同工具连续 4 次告警卡住。
- [x] M11.2.4 告警注入：检测到循环后将中文警告注入 `state["messages"]`，引导模型尝试不同策略或给出最终答案。
- [x] M11.2.5 集成点：`chat()` 入口调用 `reset()`，`_tool_loop_phase()` 每次迭代调用 `check()`。
- [x] M11.2.6 可配置参数：DEFAULT_WINDOW_SIZE=10、MIN_LOOP_REPEATS=3、MAX_SAME_TOOL_CONSECUTIVE=4。

参考来源：
- DeerFlow LoopDetectionMiddleware：基于 (tool_name, arguments) 滑窗哈希检测重复调用循环

### M11.3 记忆置信度评分

- [x] M11.3.1 `AgentMemoryBase` 新增 `confidence: float` 字段（0.0-1.0，默认 0.5）。
- [x] M11.3.2 `AgentMemory` 新增 `source: Optional[str]` 字段用于来源追踪。
- [x] M11.3.3 `MemoryManager.save_memory()` 支持 `confidence` 和 `source` 参数；已存在记忆更新时置信度自动提升 min(1.0, max(existing.confidence, new_confidence) + 0.1)。
- [x] M11.3.4 `MemoryManager.get_all_memories()` 默认按 `confidence >= 0.7` 过滤，按置信度降序排列。
- [x] M11.3.5 `MemoryManager.build_memory_context()` 增加 2000 token 预算控制，超出部分截断并附加提示。
- [x] M11.3.6 Alembic 迁移 `faf3e367bbe8`：添加 confidence（Float, NOT NULL, server_default=0.5）和 source（String(100), nullable）到 agent_memories 表。

参考来源：
- DeerFlow Structured Memory：JSON fact base 带置信度评分（0.0-1.0），重复确认渐进提升置信度，token 预算控制（top 2000 tokens 按 confidence 降序），30 秒去抖异步抽取

### M11.4 Provider Failover

- [x] M11.4.1 实现 `_build_failover_chain()`：构建优先级排序的 (provider, model) 元组列表。
- [x] M11.4.2 故障转移链：首选 profile 显式 provider/model → 同 provider_type 的激活 AIConnector → 系统默认。
- [x] M11.4.3 `_call_llm()` 遍历故障转移链，每次失败记录错误并尝试下一个 provider。
- [x] M11.4.4 全部失败时返回友好错误信息（含尝试 provider 数量）。
- [x] M11.4.5 实现 `_role_to_provider_type()`：映射 role_type 到 AI connector 的 provider_type（llm/image/video）。

参考来源：
- Hermes Provider Failover：多个推理供应商优先级排序，自动故障转移，降级到默认

### M11.5 多智能体并行执行

- [x] M11.5.1 `MultiAgentCoordinator._run_role_actors()` 从串行改为 `asyncio.gather()` 并行执行。
- [x] M11.5.2 并发上限 `MAX_PARALLEL_ROLE_ACTORS = 3`：分批处理，每批最多 3 个 actor。
- [x] M11.5.3 异常隔离：`return_exceptions=True`，单个角色失败不影响同批次其他角色。
- [x] M11.5.4 错误处理：异常 actor 创建含错误摘要的 AgentSlot，不中断流水线。

参考来源：
- DeerFlow Sub-Agent Parallel Orchestration：asyncio.gather 并发子 agent，SubagentLimitMiddleware 限制并发数（默认 3）

### M11.6 渐进式工具加载

- [x] M11.6.1 `Tool` dataclass 新增 `description_short: str` 字段。
- [x] M11.6.2 `get_openai_tools_spec()` 新增 `summary_mode` 参数，True 时优先使用 `description_short`。
- [x] M11.6.3 `register_tool()` 装饰器新增 `description_short` 参数，透传到 Tool 构造。

参考来源：
- Hermes Progressive Skill Loading：默认加载名称 + 一行摘要，完整内容按需加载（200 个 skill 的 token 开销约等于 40 个 skill）

### M11.7 验证

- [x] M11.7.1 运行测试：50 passed，0 linter 错误。
- [x] M11.7.2 Alembic 迁移 `faf3e367bbe8` 已执行 `alembic upgrade head` 成功。
- [x] M11.7.3 文档更新：docs/agent/agent-center.md 新增运行时架构优化章节。
