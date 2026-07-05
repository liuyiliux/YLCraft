# Agent Center Multi-Agent Runtime

## Why

当前智能体中心已经具备 Profile、工具注册、会话消息、基础记忆和轻量工具循环，但体验仍然接近“一问一答”。用户需要的是一个能持续推进 YLCraft 项目的执行系统：它应该能理解目标、拆分计划、选择工具、执行任务、记录结果、继续下一步，并把小说、角色、分镜、素材、生图等项目能力串起来。

结合近期调研：

- DeerFlow 2.0 倾向“多 Agent 并行编排”：总控拆任务，多个子 Agent 各自搜索、分析、写作、执行，最后汇总。
- Hermes 倾向“单 Agent 深度工作”：重视长期记忆、技能沉淀、工具注册和持续上下文。
- Codex/OpenHands 倾向“工作区执行”：明确目标、使用工具、展示轨迹、校验结果、可回看每一步。
- LangGraph 倾向“持久状态机”：run、checkpoint、human-in-the-loop、可恢复执行。
- CrewAI/AutoGen 倾向“角色化协作”：Agent、Task、Crew/Team、委派链。

YLCraft 不应先引入沉重第三方框架作为核心依赖。更稳妥的路线是：保留现有业务服务和工具注册体系，内部实现一个轻量 LangGraph/Hermes 风格 runtime，再逐步支持多 Agent 编排。

## Product Goal

把 `/agent` 从聊天页升级为“项目智能体工作室”：

- 用户说一个目标，例如“继续这个短剧项目，补小说正文、生成分镜并准备参考图”。
- 总控智能体读取项目上下文，生成可执行计划。
- 系统按步骤调用 YLCraft 工具，记录每一步输入、输出、失败原因和产物。
- 子 Agent 可以负责写作、角色、分镜、素材、质检等不同职责。
- 用户可以随时查看运行轨迹、继续、重试、取消、批准高风险动作。

## Architecture Direction

### Layer 1: Agent Profile

Profile 定义智能体身份、系统提示词、默认模型、工具白名单、默认上下文和最大步骤数。

预置角色：

- 总控导演：拆任务、分配子任务、汇总结果。
- 小说作者：大纲、细纲、正文、人味改写。
- 角色设定师：角色卡、视觉卡、参考图计划。
- 分镜导演：脚本、镜头、漫画页、图片提示词。
- 素材管家：素材检索、标签、参考图集合。
- 质检编辑：连续性、设定一致性、缺口检查。

### Layer 2: Runtime State Machine

每次执行创建一个 run，内部状态：

`intake -> context_pack -> plan -> tool_select -> execute -> observe -> decide -> final`

每一步落库为 run step，支持后续 UI 回放、失败定位、继续执行。

### Layer 3: Tool Calling

短期支持两种模式：

- JSON fallback：模型输出 `{"tool_calls":[...]}`，后端解析并执行工具。
- Native tool calling：OpenAI SDK 兼容后端返回 assistant `tool_calls`，后端按协议追加 tool result。

工具结果统一存三层：

- summary：给 UI 和下一步推理快速读。
- raw_json：完整原始返回。
- linked_objects：关联项目、章节、角色、素材、任务等业务对象。

### Layer 4: Memory And Skill

记忆分层：

- Session memory：当前会话消息。
- Project context：当前创作项目、章节、角色、素材集合。
- User preference：用户偏好，例如“小说要自然，不要 AI 腔”。
- Skill memory：可复用流程，例如“小说正文补全流程”“角色九宫格参考图流程”。

Skill 不先做复杂插件生态，先把常用创作流程固化为可配置流程模板。

### Layer 5: Multi-Agent Delegation

第一阶段不是多个进程并行跑，而是在同一 runtime 中记录委派链：

- 总控 run 创建子任务。
- 子任务绑定某个 AgentProfile。
- 子任务输出回到父 run。
- UI 展示“谁负责了什么、用了哪些工具、产出了什么”。

后续再考虑真正并行执行和队列。

### Layer 6: Workbench UI

页面应该像执行台，而不是聊天窗口：

- 左侧：Agent roster / 项目上下文。
- 中间：run 时间线、对话、计划、步骤、工具结果。
- 右侧：记忆、模型、工具权限、当前产物、失败定位。
- 工具结果默认显示摘要，原始 JSON 折叠。
- 高风险动作显示“等待确认”。

## Phased Plan

### M0: Stabilize Current Loop

目标：让当前单智能体工具循环稳定可用。

- 修复 JSON fallback 工具结果协议问题。
- 记录工具调用日志。
- 页面展示自动工具循环和工具摘要。
- 明确“未授权工具”的原因。

### M1: Durable Runs

目标：把一次对话变成可回放、可继续的执行记录。

- 新增 `agent_runs`、`agent_run_steps`。
- `AgentService.chat` 迁移到 runtime 状态机。
- 每步记录 status、input、output、error、duration、linked object。
- 页面展示 run timeline。
- 支持 retry failed step、continue run、cancel run。

### M2: Context And Memory

目标：让智能体知道“正在处理哪个项目、哪些角色、哪些素材”。

- 页面展示当前注入的 project context 和 memory。
- 会话结束后抽取可复用记忆。
- 常用创作偏好写入 `agent_memories`。
- Skill 模板支持手动选择和自动推荐。

### M3: Creative Multi-Agent Team

目标：把创作项目闭环变成多角色协作。

- AgentProfile 增加 role_type。
- 总控智能体可以创建 delegated subtask。
- 预置创作团队：总控导演、小说作者、角色设定师、分镜导演、素材管家、质检编辑。
- 创作项目页面可以一键发起“补正文 -> 补分镜 -> 匹配参考图 -> 生成图片提示词 -> 质检”的 run。

### M4: Advanced Runtime

目标：再考虑更强的 DeerFlow/OpenHands 能力。

- 原生 function calling 全链路。
- 并行子任务和队列。
- 沙箱执行代码工具。
- IM / Webhook 消息入口。
- Run checkpoint 和人工审批。

## Out Of Scope

- 暂不直接把 DeerFlow、CrewAI、AutoGen 作为核心硬依赖。
- 暂不做完全无人值守的长时间后台代理。
- 暂不自建云端执行环境。
- 暂不把所有工具开放给所有智能体，必须保留白名单和高风险确认。

## Success Criteria

- 用户能在 `/agent` 看到一次任务的完整执行过程，而不是只看到最终回答。
- 工具调用失败时，页面能定位到失败步骤、工具名、参数和错误原因。
- 智能体能读取当前创作项目上下文，并把结果写回项目。
- 一个复杂创作请求可以拆给多个专业 Profile，并保留委派链。
- 后端测试覆盖 JSON fallback、native tool calling、run step 持久化和权限拦截。

## M9: Polish & Production Hardening (2026-07-04)

M9 是对 M0-M8 产物的精修和加固，不新增架构层，重点在术语、风格、运行时深度和 Schema 质量。

**术语统一**：全系统将"步数上限/最大工具步数"替换为"迭代预算（轮）"。前端表单 label 改为"迭代预算（轮）"并附带完整 tooltip 说明，Alert 描述更新为解释计划→工具→观察→继续执行的循环含义，Profile 信息栏展示"迭代预算 N 轮"。后端 API 的 `max_steps` 字段保持数据库命名不变，但 default 从 4 提升到 8，Field description 显式说明是保护阈值而非能力上限。

**工作台风格**：降低整体卡片感，panelStyle boxShadow 置为 none，borderRadius 从 12 降至 4-6，主面板和侧边栏统一使用 flat background，消息气泡减少阴影和圆角。控制按钮从 rounded button 风格转向更细的 console 控件。

**运行时增强**：`_tool_loop_phase` 显式跟踪 `iteration`/`budget`/`remaining` 状态，预算耗尽时自动注入总结提示并触发 LLM 最终回答。`_context_pack_phase` 提取项目标题/阶段/角色/缺口摘要注入 system prompt，排在 memory 之前确保优先级。

**Schema 改进**：`register_tool` 的类型推断从简单 isinstance 升级为 `_annotation_to_json_schema`，正确处理 `list[X]`（生成 items 子 schema）、`dict`（type=object）、`Optional[T]` 和 Union 类型，减少 LLM 参数传递错误。


## M10: Phase 5 Multi-Agent Coordination (2026-07-04)

M10 实现了 creative-project-optimization-roadmap 的 Phase 5 全部 5 个任务：多智能体场景推演流水线。

**新增内置 Profile**（`profile.py`）：`role-actor`（角色演员）、`divine-director`（天意总导演）、`story-editor`（编辑润色师）。每个 profile 有明确的 role_type、system_prompt、allowed_tools 和 default_skill_ids，与前 7 个内置 profile 一致。

**MultiAgentCoordinator**（`multi_agent_coordinator.py`）：运行四阶段流水线——天意导演读取项目圣经产出行程指令 → 角色演员以角色身份生成情绪/动机/对话/行动 → 编辑润色师五维度检查 → 创作导演合成场景细纲。每个 agent 独立运行 AgentService.chat()，前序输出注入后续上下文。所有输出存为候选版本。

**API 端点**：`POST /agent/multi-agent/scene-simulation`，接收 `SceneSimulationRequest`（project_id、scene_context、characters_of_interest、iteration_budget_per_agent、store_as_candidate）。

**前端角色标签更新**：新增 `director`、`role_actor`、`editor` 三个 role_type 的中文标签。

## References

- DeerFlow: multi-agent orchestration, memory, sandbox, skill, message gateway.
- Hermes Agent: persistent memory, skill system, tool registry, long-lived agent loop.
- Codex/OpenHands: workspace, tool loop, action trace, verification.
- LangGraph: durable execution, checkpoint, human-in-the-loop.
- CrewAI/AutoGen: role-based agents, task delegation, team collaboration.
