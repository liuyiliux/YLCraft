# Implementation Plan

## Phase 0: Truthful Baseline

- [x] 0.1 Rename linear Writer Room UI/tool descriptions from “multi-agent” to “staged workflow” until team mode is active.
- [x] 0.2 Update Agent documentation to distinguish manual delegation, specialized scene coordination and autonomous Supervisor behavior.
- [x] 0.3 Add characterization tests for current parent/child runs and scene simulation defects before refactoring.

## Phase 1: Durable Delegation Core

- [x] 1.1 Add `AgentDelegation` and root/depth/run-kind fields with an Alembic migration.
- [x] 1.2 Implement `DelegationPolicy` with depth, fan-out, concurrency, timeout and root-budget enforcement.
- [x] 1.3 Implement `DelegationContextBuilder` and internal child threads that do not pollute the user-visible conversation.
- [x] 1.4 Implement `SubagentExecutor` with one independent async DB session and `AgentService` per child.
- [x] 1.5 Implement `SubagentResultAdapter`; failures must remain failures rather than output strings.
- [x] 1.6 Implement `SubagentOrchestrator` with dependency validation, parallel batches and `all`/`best_effort` joins.

## Phase 2: Supervisor Loop

- [x] 2.1 Add supervisor capability to Agent profiles and expose `delegate_agent_tasks` only to eligible profiles.
- [x] 2.2 Define and test the delegation tool schema as an internal API.
- [x] 2.3 Feed joined child observations back into the parent `RunLoop` and continue planning.
- [x] 2.4 Propagate child confirmation, cancellation and partial-failure states to the parent run.
- [x] 2.5 Route manual `/runs/{run_id}/delegate` through the common orchestrator with compatibility output.
- [x] 2.6 Add run-tree and delegation-list APIs, then regenerate API surface docs.

## Phase 3: Agent Center UX

- [x] 3.1 Render parent/child run trees inline in the conversation trace.
- [x] 3.2 Show parallel sibling state, joined summary, artifacts and failures without exposing raw payloads by default.
- [x] 3.3 Move manual delegation to a contextual run action and support “delegate and resume parent”.
- [x] 3.4 Add clear budget/depth/concurrency diagnostics.

## Phase 4: Creative Team Integration

- [x] 4.1 Add `fast` and `team` rehearsal modes while keeping the normalized `character_rehearsal` schema stable.
  - _2026-09-13 核实已实现（此前未勾）：`rehearsal_mode` 在 API（`api/v1/creative_projects.py:L413`，`default="team"`）、Agent 工具（`services/agent/tools/creative_project_tools.py:L576`）、服务（`services/creative_project/service.py:L2299`）三层贯通；归一化 `character_rehearsal` schema 未变。_
- [x] 4.2 Resolve participating characters from project facts and allow explicit user selection.
  - _已实现：`_run_character_rehearsal_team` 以 `_resolve_team_characters(project.id, context)` 解析参与角色（`service.py:L2656`）；显式传入走 `character_ids`（`services/creative_project/schemas.py:L458`）。_
- [x] 4.3 Run one role-actor child per character, then editor join, with independent sessions and bounded parallelism.
  - _已实现：`writer-room-team` 模板经 `TeamComposer.run(...)` 执行（`service.py:L2684`）；`SubagentExecutor(AsyncSessionLocal)` 保证每个子 Agent 独立会话（L2681）；汇合后**逐条抽取 role-actor 输出**（L2696 原注释：`Extract each role-actor's independent output (one child per character)`）。_
- [x] 4.4 Store run provenance on the rehearsal candidate and keep promotion/manual canon rules unchanged.
  - _已实现：每条 performance 带 `child_run_id`（`service.py:L2706-2710`），父 Run 为独立持久化 `AgentRun(profile_id="creative-director", run_kind="primary")`（L2668）；候选仍按原有 promotion / 人工正典规则处理。_
- [x] 4.5 Add Story UI mode control and inline team progress.
  - _已实现：`writer-room.tsx` 的 Segmented 提供「角色团队推演（每角色子智能体）」/「快速演绎（单模型）」，经 `StoryWorkspaceShell.tsx:L169` 与 `useStoryPageContext.tsx:L32` 贯通；团队进度由 `TeamRehearsalPanel`（`writer-room-parts.tsx:L128`）内联展示。_
- [x] 4.6 Migrate `MultiAgentCoordinator` to a declarative team template and remove duplicate unsafe execution logic.
  - _已实现：`MultiAgentCoordinator` 现为 `TeamComposer` 之上的薄门面（`team_composer.py:L21`），端点走 `run_team("scene-sim")`；重复的硬编码执行逻辑已移除（详见 `agent-team-composition` 5.4，实测 5/5 与 4/4 子运行完成）。_

## Phase 5: Audit And Closure

- [x] 5.1 Audit CutClaw and other domain “agent” loops; link telemetry where useful without forcing them into Supervisor semantics.
  - _2026-09-13 审计完成：_
    - _域内"agent 循环"实测**只有 CutClaw 一处**：`services/clip/cutclaw_service.py:L200 class CutClawAgent`，其模块注释自述为"自然语言指令驱动，LLM 工具调用循环"。_
    - _它**已经接入**统一层，无需改造：通过 Agent 工具 `start_cutclaw_clip` 暴露（`services/agent/tools/__init__.py:L9`、`clip_tools.py:L10`、`runtime/skills.py:L52` 映射到 `clip_workflow`）；事件日志亦有归类（`api/v1/logs.py:L400` 将 cutclaw 与剪辑类场景归并）。_
    - _其余"loop/agent"命名命中均为 **agent 域自身**（`runtime/loop.py` 的 `RunLoop`、`loop_detector.py` 的 `LoopDetector`、`AgentService`/`AgentScope`/`AgentProfileManager`/`AgentSkillDraftService`），不是别的域自造运行时。_
    - _**结论**：CutClaw 保持独立域实现 + 既有工具入口与日志接入，**不强行纳入 Supervisor 语义** —— 与任务要求一致，无需新增改动。_
- [x] 5.2 Audit all UI labels, docs, tools and OpenSpec claims for “multi-agent” accuracy.
  - _2026-09-13 审计完成（含一处修正）：_
    - _**前端 UI 仅 1 处**使用"多智能体"：`pages/story/utils.ts:L97` 的 `scene_simulation_candidate: '多智能体候选'` —— **表述准确**（场景推演确实产生独立子 Run），无需改。_
    - _**文档无一处把 Writer Room 的线性流水线误称为多智能体**（逐段落交叉检索"多智能体/多 Agent"与"Writer Room/流水线/staged"，命中 5 处全部准确：`docs/README.md:L51` 描述已落地的团队组合能力、`YLCRAFT_SYSTEM_ARCHITECTURE.md:L233/L235` 描述委派续跑与运行时骨架、`AI_NOVEL_OPEN_SOURCE_RESEARCH.md:L9` 是"不引入多 Agent 框架"的决策记录、`docs/DESIGN.md:L88` 描述的是**参考项目** ai-fusion-video 而非本项目）。说明 Phase 0.1 的整改有效。_
    - _**发现并修正一处"反向失真"**：`docs/agent/agent-center.md` 的「当前多智能体边界」段**已过时且方向是低报**——原文称"Writer Room 的角色演绎仍是单模型结构化推演"与"`MultiAgentCoordinator` 尚未迁移到统一运行时"，而这两条**均已不成立**（`rehearsal_mode` 默认 `team` 且 UI 有模式控制；Coordinator 已迁到 `TeamComposer`）。已改写为按实现描述，并**如实标注**"Writer Room 的 team 模式仍待一次真实项目运行验证"。同时补上该 change spec 的 `Requirement: Truthful Multi-Agent Presentation` 口径：带持久子 Run 的场景推演与团队排练可按多智能体描述，**但必须同时暴露 responsible profiles 与 run tree 作为证据**；Writer Room 其余工序仍表述为分阶段工作流。_
    - _活跃 OpenSpec 内 18 处命中均为**对本 change 目标的描述**（如 proposal 自述"three behaviors described as multi-agent"、spec 的 Truthful 需求），属正常。_
- [x] 5.3 Add focused backend tests for delegation, transaction isolation, parent resume, confirmation and Writer Room team mode.
  - _2026-09-13 核实：**五项均有专项测试**（此前误判为缺 parent resume / confirmation，见末尾说明），`pytest -k "delegat or team or resume or confirmation or cancellation or parent or orchestrator or scope or capability or cost_meter or compressor"` → **48 passed**。_
    - **delegation**：`test_agent_delegate_subtask_creates_child_run_and_parent_step`（`test_agent_center.py:L2995`）、`test_delegation_policy_rejects_cycles_and_depth_overflow`（L3041）、`test_delegation_tool_schema_and_supervisor_visibility`（L3137）、`test_delegated_task_parses_spawn_mode` / `_rejects_invalid_spawn_mode`
    - **transaction / 作用域隔离**：`test_agent_scope_child_isolates_agent_state`（子作用域共享 host 单例但隔离 agent 状态）、`test_subagent_orchestrator_runs_independent_tasks_in_parallel`（L3114）
    - **parent resume**：`test_supervisor_delegation_result_resumes_parent_loop`（L3261）、`test_manual_delegation_observation_resumes_same_parent_run`（L3324，直接驱动 `resume_from_delegation_observation`）
    - **confirmation 传播**：`test_child_confirmation_and_cancellation_propagate_to_parent_join`（L3430）
    - **Writer Room team mode**：`test_build_tasks_writer_room_resolution` + `test_writer_room_team_helpers.py` 5 例（角色解析、场景上下文）
    - 另有：`test_agent_run_tree_and_delegation_apis`（L3375）、模板三校验（cycle / missing join / invalid spawn）、`test_capability_diff_detects_*` 2 例、`test_tool_registry_deterministic_ordering`、`test_context_compressor_records_provenance`、`test_cost_meter_reads_*` 5 例（含 DeepSeek cache hit）
  - _本次补强：向 `test_delegation_primitives.py` 追加 **4 例** `joined_observation` 状态呈现测试（`waiting_confirmation` / `cancelled` / `skipped` / `failed` / 无回复 / 截断），断言**不得被渲染成"已完成"**——既有 3 例只覆盖 fork 与 `send_message` 原语，状态分支未被碰过；若把 `waiting_confirmation` 渲染成成功文本，父级会误以为子任务完成（正是本 change 要防的"失败被降级成普通文本"）。该文件现 **7 passed**。_
  - _**关于此前误判**：我曾用正则 `^def (test_\w+)` 检索测试函数名，得出"parent resume / confirmation 无专项测试"。实际这些用例是 `async def test_...`，**`^def` 匹配不到 `async def`**，因此漏检。同一写法陷阱本次会话内已踩两次（另一次在统计 `test_delegation_primitives.py` 时）。**统计 Python 测试函数必须匹配 `^(async )?def`**。_
- [ ] 5.4 Run frontend typecheck/build and external-browser smoke for Agent Center and Story.
- [ ] 5.5 Update architecture, Agent runtime guide, API surface and current project status before archiving the change.
