# Implementation Plan

## Phase 1: Host/Agent Plane Boundary

- [x] 1.1 Add `AgentScope` (contextvars-based) with `host` and `agent` namespaces; bind process singletons under `host`.
- [x] 1.2 Migrate per-session state (persona, plan-mode, compaction) behind `AgentScope.agent` so role actors no longer share mutable instances. (Scope container shipped; `AgentService` wiring is a follow-up.)
  - _2026-09-13 完成接线：_
    - _`scope.py` 新增 `AgentScope.enter_scope(scope)`（安装**已有**作用域，退出/异常均恢复上一层），`enter()` 改为复用它。这是必要接缝：调用方需要先 `child()` 派生出「继承 host 与团队上下文、隔离 agent 平面」的作用域，再把**它**装上，而不是另造一个空作用域。_
    - _`AgentService` 新增 `_agent_scope(role_id=..., **overrides)`：发布 per-session 状态到 agent 平面（`compressor`/`loop_detector`/`planner`/`tool_executor`/`skill_router`/`context_assembler`/`user_id`）；若当前已在作用域内则 `child()` 派生（共享 host 字典、**复制** agent 字典），否则建根作用域并在 host 平面发布进程级单例 `ToolRegistry`。_
    - _`chat()` 改为安装该作用域后执行，原实现整体改名为 `_chat_pipeline`（**未改动正文**，仅改 def 名 + 新增 13 行包装），因此语义等价、风险可控。效果：作用域覆盖整轮对话，深层代码可用 `AgentScope.current()` 解析本会话状态而不必逐层透传；角色子会话（`team_composer.service_factory` 建出的 child `AgentService`）经 `child()` 拿到**隔离的** agent 平面，同时继承 `team_template`/`join_strategy`。_
    - _**一处必须说清的事实**：接线前复核发现，"role actors 共享可变实例"这个风险**当时并不成立**——`AgentService.__init__` 的状态全部是实例级，且 `app/services/agent/` 下**不存在模块级可变状态**（唯一进程级单例是 `services/ai/service.py` 的 `_ai_service`，本就属 host 平面）。因此本条的价值是把隔离**从"约定"变成"结构保证"**（并让深层代码可解析作用域），而不是修复一个正在发生的缺陷。per-session 状态仍以实例属性为准，作用域持有的是引用。_
    - _测试：新增 4 例——`enter_scope` 的安装与恢复、异常路径恢复、`chat()` 确实安装作用域且退出后不泄漏（monkeypatch 捕获，不触发 LLM）、团队作用域内派生时继承 host/团队上下文并隔离 agent 平面。实测 scope 相关 **5 passed**；`pytest -k "agent or team or compressor or planner or delegation or scope"` → **192 passed / 2 skipped**。_
- [x] 1.3 Add characterization tests proving child scopes share host singletons but isolate agent state.

## Phase 2: Team Template Schema

- [x] 2.1 Define `TeamTemplate` / `RoleSpec` models matching the YAML schema (profile, spawn, resolve, parallel, depends_on, join, budget).
- [x] 2.2 Implement `TeamTemplateLoader` and `TeamTemplateValidator` (dependency refs, single join, template-role requires resolve, budget caps, cycle detection).
- [x] 2.3 Ship `writer-room-team` and `scene-sim` templates; unit-test load + validation failures (cycle, missing join, unknown spawn).
- [ ] 2.4 Record immutable provenance and a declared capability diff per template role; route template/role capability changes through draft approval. (`capability_diff` + tests shipped; draft-approval routing is the remaining follow-up.)

## Phase 3: Subagent Primitives

- [x] 3.1 Add `ForkExecutor` (read-only parent context reference + role instructions) beside the spawn `SubagentExecutor`.
- [x] 3.2 Add `spawn_mode` and `continuation_of` to `AgentDelegation` + Alembic migration (`012_add_team_composition_fields`).
- [x] 3.3 Add `send_message(subagent_id, message)` continuation entry routing through the common orchestrator.
- [x] 3.4 Integration-test fork snapshot and continuation persistence end-to-end. (Fake-backed contract tests shipped for `ForkExecutor`/`send_message`; live end-to-end verified via the scene-sim team run — 5 isolated child runs with fork/spawn all completed against real DeepSeek.)

## Phase 4: Cache-Stable Tool Catalog

- [x] 4.1 Emit tool schemas in lexicographic name order; assert byte-identical assembly for an unchanged tool set.
- [ ] 4.2 Keep the tool catalog unchanged across plan/batch modes; override behavior via instruction text instead of removing tools. (No plan/batch mode exists yet; ordering is the current prefix-stability guarantee.)
  - _2026-09-13 复核：**本条当前无实现对象，保持未勾**。原文自述"No plan/batch mode exists yet"，本轮复核确认该前提仍未出现——`plan_mode`/`batch_mode` 在 `backend/app` 下检索为 0 命中（命中的 `plan` 均为 novel_sources 的导入计划与创作项目的内容计划，与本条无关），`scope.py` 仅在其 docstring 里把 plan-mode 列为 `AgentScope` 的覆盖目标。_
  - _因此本条的约束当前**空洞成立**（不存在模式切换，工具目录自然不会因模式而变），前缀稳定性由 4.1 的字典序 + 字节级一致性断言保证。待真正引入 plan/batch 模式时，本条才可执行；届时须同时验证模式切换不改变工具目录。_
- [x] 4.3 Carry explicit `system_prompt_ref`/`tool_schema_ref` on compacted requests. (Prefix reuse is enforced via deterministic ordering; explicit refs pending.)
  - _2026-09-13 实现：_
    - _新增模块级 `stable_ref(payload)`（`context_compressor.py`）：对 prompt/schema 载体取**字节级稳定**的短引用（结构体走规范化 JSON——键排序、紧凑分隔符、非 ASCII 不转义，再取 sha256 前 12 位）。稳定性是硬要求：同一输入在任何进程/时刻必须得到同值，否则引用本身会成为前缀缓存的不稳定源。_
    - _`ensure_fits()` 新增可选 `system_prompt_ref` / `tool_schema_ref`，并透传给 `_compress()`；`_last_provenance` 记入两者。语义上刻意区分"未提供"与"提供了但为空"：未提供时 `system_prompt_ref` 按系统提示**内容自算**（不留空），`tool_schema_ref` 记为常量 `unspecified`。_
    - _调用方 `runtime/planner.py`：把 `ToolRegistry.get_openai_tools_spec(...)` **提前到压缩之前**构造（字典序、字节级稳定，提前取用不改变请求前缀），并以 `stable_ref(system_text)` / `stable_ref(tools)` 显式传入。_
    - _这填补的正是原注释的**可验证性缺口**：代码声称"系统提示与工具 schema 块保持确定性以便前缀复用"，但溯源里只有 `source_span`/`summary_version`/`expansion_path`，无法指名压缩是在哪一版 prompt/schema 下产生的。_
    - _测试（`tests/test_team_composition.py` 新增 3 例）：`stable_ref` 的稳定性与内容敏感性（含键序无关、空值不抛错、长度 12）；显式 ref 原样落到溯源；未显式传时 system_prompt_ref 自算且随内容变化、tool_schema_ref 为 `unspecified`。实测 **26 passed**；`pytest -k "agent or team or compressor or planner or delegation"` → **182 passed / 2 skipped**。_
- [x] 4.4 Record `source_span`/`summary_version`/`expansion_path` on compaction output so compression is traceable.
- [x] 4.5 Add `CostMeter` reading cached vs total prompt tokens; surface cache-hit % in run diagnostics.

## Phase 5: Integration

- [x] 5.1 Implement `TeamComposer.run(template_id, inputs)` over `SubagentOrchestrator` (topological batches, joins, budget enforcement).
- [x] 5.2 Route `MultiAgentCoordinator` endpoint through the declarative composer. (`run_team` facade and `use_team_template` opt-in flag shipped; endpoint defaults to the legacy path until compatibility tests pass.)
  - _2026-09-13 核实：**本条已满足，且原备注已过时**——它写"endpoint 在兼容测试通过前仍走 legacy 路径"，但 legacy 路径已被 5.4 整体删除，因此不存在"可切换的默认路径"。_
    - _端点单一路径：`api/v1/agent.py:L2047` 直接 `await coordinator.run_team("scene-sim", config)` 并返回，**无任何分支判断**。_
    - _`MultiAgentCoordinator` 公开面仅剩 `__init__` / `run_team` / `_store_team_candidate`；`run_team` 内部导入并使用 `TeamComposer` + `SubagentExecutor` + `SubagentOrchestrator`（`multi_agent_coordinator.py:L63-64`），构建独立子会话的 `service_factory`（L89-94）。_
    - _旧符号全库检索均为 **0 处**：`AgentSlot`、`_store_candidate`、`use_team_template`（opt-in 开关本身已不存在）、`_run_hardcoded`。_
    - _兼容性由既有测试覆盖：`pytest -k "multi_agent or team_composition or scene_sim"` → **25 passed**。_
- [x] 5.3 Wire Writer Room `team` rehearsal mode to `writer-room-team`; persist `character_rehearsal` candidate with team provenance. (Implemented as opt-in `rehearsal_mode="team"`, threaded through API, tool and service; `_run_character_rehearsal_team` resolves characters, runs `TeamComposer` over `writer-room-team` in an async `SubagentOrchestrator`, and persists the joined observation as `character_rehearsal`. Team orchestration verified live via `scene-sim`; writer-room team still needs one real-project run.)
- [x] 5.4 Remove duplicate unsafe execution logic after compatibility coverage passes. (Legacy `run_scene_simulation` + hard-coded step methods + `AgentSlot` + `_store_candidate` removed; endpoint now always routes through `run_team("scene-sim")`. Verified live: 5/5 and 4/4 child runs completed via the declarative team path.)

## Phase 6: Validation And Closure

- [x] 6.1 Add focused backend tests (15) for template validation, scope isolation, spawn_mode parsing, cache-stable catalog, compression provenance, cost metering.
- [x] 6.2 External-browser smoke for Agent Center and Story team mode (no frontend changes in this change; UI mode control belongs to `agent-supervisor-subagent-runtime` Phase 4.5).
  - _2026-09-13 通过（Patchright + Chromium 1600×1050）。前置已解除：本条阻塞于 `agent-supervisor-subagent-runtime` Phase 4.5 的 UI 模式控制，该 change 已于同日归档。_
    - **Agent Center `/agent`**：HTTP 200；正文含「智能体 / 对话 / 新对话」；点开会话后页面存在 **15 个 `<details>` 折叠块**（运行执行过程内联展开位）。
    - **Story team 模式**：`/story` HTTP 200 → 点「单章工作室」→ 点「写作室」tab；分段控件实测为 **`['角色团队推演（每角色子智能体）', '快速演绎（单模型）']`**，与 Phase 4.5 要求的 team/fast 双模式一致；「角色团队推演（每角色子智能体）」与「快速演绎（单模型）」文案均在页面上；团队进度面板容器存在（`TeamRehearsalPanel`）。
    - **全程 0 个 >=400 响应、0 条控制台 error**。
    - 纯只读验证：未触发生成，未消耗任何额度。
- [x] 6.3 Update architecture, project status and OpenSpec records.
