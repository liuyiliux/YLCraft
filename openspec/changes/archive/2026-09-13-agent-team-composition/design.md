# Design: Declarative Agent Team Composition

本设计借鉴 DeepSeek Harness（DSH，Cordis 插件框架）的「声明式组合 + 主机/代理双层平面 + 子代理三原语 + 前缀缓存稳定」，在 YLCraft 的 Python/FastAPI/SQLModel 语境下原生落地。它叠加在 `agent-supervisor-subagent-runtime` 之上，是该 change Phase 4.6 的实现依据。

## 1. Design Principles

1. **组合优于硬编码**：团队 = 角色清单 + 依赖 + 预算，由模板描述；运行时只做实例化、调度、连接。
2. **主机平面与代理平面分离**：进程级单例（注册表、持久化、沙箱、模型路由）不进 per-session；per-session 状态（persona、计划、压缩、委派工具）不进全局。
3. **原语正交**：`spawn` / `fork` 与 `continuable` 是三个独立维度，不绑死在某个编排路径里。
4. **前缀缓存稳定**：工具目录按名称字典序、字节级确定；模式切换不增删工具；压缩复用同一前缀。
5. **能力可降级**：模板校验失败、运行时缺失、预算超限都要以结构化失败呈现，不静默降级为普通文本。

## 2. Host Plane vs Agent Plane

DSH 用 `isolate` 域把「进程级单例」与「per-session 实例」分开。Python 侧用**显式作用域容器**复刻，而不是依赖模块级全局。

### 2.1 边界表

| 关注点 | 归属 | 落地位置 |
| --- | --- | --- |
| 工具注册表 | 主机平面（进程单例） | `services/agent/registry.py` |
| 技能注册表 | 主机平面 | `services/agent/skill_loader.py` |
| 子代理注册表 / 执行后端 | 主机平面 | `services/agent/runtime/delegation.py` |
| 持久化 / 会话存储 | 主机平面 | `services/agent/session/manager.py`、`db` |
| 模型路由 / 成本计量 | 主机平面 | `services/ai/router` + 新增 `CostMeter` |
| 沙箱 / 审批栈 | 主机平面 | 工具风险分级 + 确认边界 |
| persona / instructions | 代理平面（per-session） | `services/agent/profile.py` 实例化 |
| 计划模式状态 | 代理平面 | 新增 `PlanModeState` |
| 压缩 / 上下文状态 | 代理平面 | `services/agent/context_compressor.py` 实例 |
| 团队模板实例 | 代理平面（每次团队运行一份） | 新增 `TeamComposer` 运行上下文 |

### 2.2 作用域隔离机制

引入 `AgentScope`（基于 `contextvars.ContextVar`）作为 per-session 作用域键：

- 主机平面服务用 `scope.get("tools")`、`scope.get("subagents")` 解析，这些键始终绑定到进程单例。
- 代理平面服务用 `scope.get("persona")`、`scope.get("plan_mode")`、`scope.get("compaction")`，只在当前 session 内可见。
- 团队运行创建子作用域 `scope.child(role_id=...)`，子作用域可见主机平面单例，但每个角色的 `persona`/`compaction` 是独立实例。
- 同名服务在**不同角色作用域**下不共享可变实例；这替代 `MultiAgentCoordinator` 当前共享会话的坏味道。

## 3. Declarative Team Template

### 3.1 Schema

```yaml
team:
  name: writer-room-team
  version: 1
  roles:
    - id: director
      profile: director
      persona: "你负责拆解本场冲突，给每个角色下发独立视角任务。"
      tools: [novel_tools, character_tools]
      skills: [ylcraft-novel-writer-room]
      spawn: fork                 # fork | spawn
      parallel: false

    - id: role-actor
      profile: role-actor
      template: true              # 按 resolve 结果，每项实例化一个子代理
      resolve:
        source: project_characters
        allow_user_selection: true
      spawn: spawn
      parallel: true
      max_parallel: 3
      depends_on: [director]

    - id: editor
      profile: editor
      spawn: fork
      parallel: false
      depends_on: [role-actor]
      join: true                  # 编辑角色负责连接并输出单一候选
  join_strategy: all              # all | best_effort
  budget:
    max_depth: 2
    max_children: 6
    max_concurrent: 3
    timeout_s: 300
```

### 3.2 字段语义

| 字段 | 含义 |
| --- | --- |
| `profile` | 复用现有 Agent profile（含 supervisor 能力位、工具 allowlist）。 |
| `spawn` | `spawn`=全新子会话（冻结有界上下文快照）；`fork`=继承父上下文（评审/编辑视角）。 |
| `template` + `resolve` | 声明式展开：`project_characters` 从项目事实解析角色列表，逐项实例化 `role-actor`。 |
| `parallel` / `max_parallel` | 是否并行 + 并发上限，由 `DelegationPolicy` 执行，而非提示词。 |
| `depends_on` | 拓扑依赖，由 `SubagentOrchestrator` 校验（拒绝环）。 |
| `join` | 标记连接角色；其输出经 `SubagentResultAdapter` 归一化为单一候选。 |
| `budget` | 复用 `DelegationPolicy` 的 depth/fan-out/concurrency/timeout/root-budget。 |

### 3.3 加载与校验

- `TeamTemplateLoader`：从 `backend/app/agent_teams/*.yml`（或 DB 草稿）加载，解析为 `TeamTemplate` Pydantic 模型。
- `TeamTemplateValidator`：启动时与运行时各校验一次——`depends_on` 引用存在、`join` 恰好一个、`template` 角色必须带 `resolve`、预算在全局上限内、profile 存在。
- 校验失败返回结构化错误，绝不 fallback 到旧的硬编码执行路径（避免静默回归）。

### 3.4 能力来源与审批

模板挂载的每个角色，其 `profile` + `tools` + `skills` 都是一次「能力授权」，不是纯声明：

- 每个能力的来源要有 immutable provenance（哪个模板、哪个版本、来自仓库还是 DB 草稿）。
- 模板变更生成**能力 diff**（新增 / 移除 / 升级了哪些工具或技能），进入审批，而非静默生效。
- 运行时按 diff 与审批结果挂载能力，避免「热插拔式」静默扩大权限——挂载即权限变更（对应 DSH 的 supply-chain 批评）。
- 复用现有 Skill 草稿审批链路：模板与角色能力变更先落草稿、批准后生效。

## 4. Subagent Primitives

复用 `agent-supervisor-subagent-runtime` 的 `SubagentOrchestrator` / `SubagentExecutor` / `DelegationPolicy`，新增两个原语：

### 4.1 `fork`（继承父上下文）

- 现有 `SubagentExecutor` 是 `spawn`：新建独立 session，注入冻结有界快照。
- 新增 `ForkExecutor`：子会话以父上下文的**只读引用**为起点，增量追加角色指令；不复制整条聊天，只挂有界快照 + 角色上下文。
- 适用：编辑 join、评审、基于父结果的二次推理。DSH 中 `subagent_fork` 是同一实现、不同 provider 参数。

### 4.2 `continuable`（可续跑）

- 子代理默认后台运行，返回 durable 子代理 id（对应 `AgentDelegation.child_run_id`）。
- 新增 `send_message(subagent_id, message)`：对已存在子会话追加续跑，不重开、不丢失已生成的中间产物。
- 适用：编辑 join 后要求某个角色补一段、父计划循环中对子结果追问。

### 4.3 与现有组件的映射

| DSH 原语 | YLCraft 落地 |
| --- | --- |
| `spawn` provider | `SubagentExecutor`（已有） |
| `fork` provider | 新增 `ForkExecutor` |
| `continuable` backgroundMode | `AgentDelegation` 增加 `spawn_mode` + `send_message` 入口 |
| 同一实现多 toolName | 一个 `TeamComposer` 暴露 `spawn`/`fork` 两种入参 |

## 5. Prefix-Cache Stability（前缀缓存稳定）

DSH 把「token 影响 vs KV 缓存影响」拆成两个维度逐项记录。YLCraft 落地为四条硬规则：

### 5.1 确定性工具目录拼装

- 工具 schema 在请求组装时按**工具名字典序**排序，序列化时禁止非确定性字段（dict 保持插入序、无 set 遍历、无时间戳进 schema）。
- 未变更的工具集 + 未变更的顺序 ⇒ 字节级相同的 schema 前缀 ⇒ 命中 LLM KV 缓存。
- 落地：`registry.py` 输出工具目录改为 `sorted(tools, key=lambda t: t.name)`，并加回归测试断言「同一工具集两次拼装字节相同」。

### 5.2 模式切换不增删工具

- 计划模式、Code/批量模式等**不改变工具目录**：变更工具保留在目录里，通过追加的指令文本覆盖行为（DSH plan-mode 原文策略）。
- 收益：工具目录稳定，请求前缀可复用；「隐藏工具」会破坏从第一个变动的 schema token 起的缓存复用，故只在真正禁用能力时才移出目录。

### 5.3 压缩复用同一前缀

- `context_compressor.py` 压缩后，请求**仍复用同一系统提示词 + 工具 schema 块**作为前缀，只替换消息体。
- 新增字段约定：压缩产物携带 `system_prompt_ref` 与 `tool_schema_ref`，指向未变的稳定前缀，保证压缩不导致缓存失效。
- 压缩是有损状态迁移，不是纯效率优化：压缩产物必须额外携带**源 span 引用 + 摘要版本 + 确定性展开路径**，让运行时能指认「哪些原始观测被保留、哪些被折叠」；否则等于制造了无版本的记忆替身（对应社区的 compression-is-state-corruption 批评）。

### 5.4 缓存命中率观测与进阶

- `CostMeter`（主机平面）从 provider 返回的 `usage.prompt_tokens_details.cached_tokens` / `total_tokens` 计算命中率，随任务观测诊断（`task-observability-diagnostics`）落库。
- Agent 运行详情页展示「缓存命中 %」，作为前缀稳定性回归的看板指标。
- 进阶方向（非本期范围）：本设计先做到「字节级稳定前缀」；社区已有更强方案 Prompt Choreography，把 KV cache 当作可重排的编码池，让多 agent 复用彼此前缀，TTFT 快 2.0–6.2x。作为后续演进目标（见 §11）。

## 6. Persistence

在 `AgentDelegation`（`agent-supervisor-subagent-runtime` 已定义）上追加：

| 字段 | 用途 |
| --- | --- |
| `spawn_mode` | `spawn` 或 `fork` |
| `team_template_id` | 来源模板 id（+ 版本） |
| `role_id` | 角色在模板中的 id |
| `continuation_of` | 续跑时指向被续的子代理 |

不新增独立表；团队模板本身存 YAML（仓库内）或 DB 草稿（复用 Skill 草稿审批模式），运行实例用 `AgentDelegation` + `AgentRun.run_kind=team_stage` 记录。

## 7. Integration

### 7.1 MultiAgentCoordinator 迁移

- `MultiAgentCoordinator` 保留为 HTTP 兼容门面，内部改为 `TeamComposer.run(template_id="scene-sim", ...)`。
- 旧端点输出形状不变；兼容测试通过后删除门面背后的重复执行代码。

### 7.2 Writer Room 团队排练

- `character_rehearsal` 的 `team` 模式复用 `writer-room-team` 模板：director（fork 简报）→ 每角色一个 role-actor（spawn 并行）→ editor（fork 连接）。
- 结果照旧存为 `character_rehearsal` 候选，带 `root_run_id` / 子 run / 模板 id 溯源；不覆盖已批准正文或锁定事实。

## 8. UI

- Story 的角色排练步显示 `快速演绎 / 角色团队推演` 分段控件（复用 `agent-supervisor` Phase 4.5 的 Story UI 模式控制）。
- 团队模式内联展示：选中的角色、并行子代理状态、编辑 join 状态。
- Agent Center 运行树沿用 `agent-supervisor` Phase 3 的内联子 run 展示，新增 `spawn/fork` 徽标与缓存命中率。

## 9. Migration

1. 引入 `AgentScope`，把现有全局注册表收进主机平面（不改变外部行为）。
2. 新增团队模板 schema + loader + validator，无运行时使用。
3. 新增 `fork` 与 `continuable` 原语（`ForkExecutor` + `send_message`）。
4. 工具目录确定性拼装 + 缓存命中观测，加回归测试。
5. 把 `MultiAgentCoordinator` 门面切到 `TeamComposer`。
6. Writer Room `team` 模式接入模板。
7. 兼容测试通过后删除旧的协调器执行代码。

## 10. Validation Strategy

- 单元：模板加载/校验（依赖环、join 唯一性、预算上限）、工具目录字节级确定性。
- 异步：并发角色子代理使用独立会话与事务；一个失败不污染兄弟。
- 运行时：`fork` 可见父上下文有界快照；`continuable` 续跑保留中间产物。
- 缓存：同一工具集两次拼装字节相同；压缩前后系统提示词 + 工具 schema 前缀不变。
- API/UI：`agent-supervisor` Phase 5.3/5.4 的委托、父续跑、确认、Writer Room team 模式测试；前端 typecheck/build + 外部浏览器冒烟。

## 11. Prior Art And Related Work

本设计的方向不是 harness 独有，而是社区独立收敛的共识。以下为检索到的高相关讨论，作为设计依据与边界来源：

| 来源 | 与本设计的关系 |
| --- | --- |
| [Cordis – DeepSeek Harness Plugin Architecture](https://github.com/cordiverse/paper/blob/main/paper.pdf)（论文） | 权威参考：Cordis 内核只做插件生命周期，能力以插件组合。本设计借鉴其「声明式组合 + 双层平面」。 |
| neo_konsi_s2bw《Context compression is a state-corruption bug, not an efficiency feature》 | 批评压缩是有损状态迁移；主张 source span + summary version + 确定性展开路径。→ 落入 §5.3。 |
| neo_konsi_s2bw《Hot-swappable plugins turn permissions into a supply-chain bug》 | 热插拔即权限变更；要求 immutable provenance + 能力 diff + 审批边界。→ 落入 §3.4。 |
| nanomeow_bot《The Disaggregated Agent Runtime: Decoupling the Cognitive and Execution Planes》 | 独立提出 Cognitive / Execution / Orchestration 三层，等价于本设计的 host/agent 平面；其 Capability Registry（MCP/A2A 动态发现）为本设计长期演进。 |
| vina《KV cache re-computation is a tax on multi-agent workflows》（125 赞） | Prompt Choreography：KV cache 作为可重排编码池，跨 agent 复用前缀。→ §5.4 进阶方向。引用 Bai & Eisner (2026), TACL。 |
| auroras_happycapy《Workflow Orchestration and Pipeline Design for Complex AI Agent Tasks》 | 声明式 DAG、fan-out/fan-in、Saga 补偿、版本化、工作流编译；作为 §3/§7 执行层实现参考。 |

三点影响已回填：**验证**（host/agent 平面 + 声明式组合 + 前缀缓存稳定是独立收敛共识）、**补强**（压缩溯源 §5.3 + 能力审批 §3.4）、**升级**（缓存进阶 §5.4 + Capability Registry 演进）。
