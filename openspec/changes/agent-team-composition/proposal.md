# Declarative Agent Team Composition

## Why

YLCraft 目前的 Agent 团队能力有三个结构性问题：

1. **硬编码编排**：`backend/app/services/agent/multi_agent_coordinator.py` 把「导演 / 角色演员 / 编辑 / 编剧」写死成命令式代码，共享同一个 async 数据库会话，忽略 per-agent 预算，且失败可能被降级成普通文本。这与 `docs/README.md` 标注的待办「把 `MultiAgentCoordinator` 迁移为声明式团队模板、移除重复不安全执行逻辑」直接对应。
2. **缺少全局/会话边界**：工具注册表（`registry.py`）、技能注册表、子代理注册表都是进程级单例，而 persona、instructions、计划模式、压缩状态本应是 per-session。当前没有显式边界，新增一个团队角色时容易产生跨会话状态串扰。
3. **工具目录缓存不稳定**：工具 schema 的拼装顺序与内容未做确定性约束，模式切换（如计划模式）若增删工具会破坏 LLM 前缀缓存，导致每次请求重新计费、延迟上升。当前没有任何「token 影响 vs 缓存影响」的工程纪律。

`agent-supervisor-subagent-runtime` 已交付子代理运行时机制（`SubagentOrchestrator`、`SubagentExecutor`、`DelegationPolicy`、持久化），但缺一套**声明式团队组合模型**来替换硬编码编排，也缺 `fork`（继承父上下文）与「可续跑」原语，以及缓存稳定性规则。

## Product Goal

- 团队由一份可复用、可校验的声明式模板（YAML）描述，而非命令式代码。
- 明确区分**主机平面**（进程级单例注册表）与**代理平面**（per-session 状态），用显式作用域隔离替代模块级全局。
- 子代理具备三种正交原语：`spawn`（全新会话）、`fork`（继承父上下文）、`continuable`（可续跑同会话）。
- 工具目录拼装确定性（按名称字典序、字节级稳定），并把「token 影响 vs 前缀缓存影响」固化为每个设计决策的收尾检查项。
- `MultiAgentCoordinator` 变成声明式模板之上的兼容薄壳，Writer Room `team` 排练模式复用同一模板。

## Scope

- 新增团队模板 schema、加载器与静态校验器。
- 新增 `TeamComposer`：解析模板 → 实例化角色 → 通过 `SubagentOrchestrator` 执行 → 连接（join）。
- 把工具/技能/子代理注册表明确划入主机平面，persona/instructions/计划/压缩状态划入代理平面，并用作用域容器隔离。
- 新增 `fork` 子代理原语与 `continuable` 续跑入口。
- 工具目录确定性拼装 + 缓存命中率观测。
- 迁移 `MultiAgentCoordinator` 为兼容门面，接入 Writer Room `team` 模式。

## Non-Goals

- 不引入 Cordis、LangGraph、CrewAI、AutoGen 或任何 Node 插件框架；只借鉴「声明式组合 + 平面边界」的思想，在 Python/FastAPI/SQLModel 上原生实现。
- 不把插件打包成独立可安装包；模板与注册表用仓库内 YAML + Python 注册即可。
- 不把确定性生产阶段（发布、资产写、章节晋升、固定流水线）改成子代理。
- 不实现进程外沙箱（那是独立的后续议题）；本设计只明确风险分层与确认边界。
- 不改变 `agent-supervisor-subagent-runtime` 已定的持久化与预算语义，只在其上叠加组合层。

## Success Criteria

- 同一份 `writer-room-team` 模板能同时驱动场景模拟（`MultiAgentCoordinator` 兼容门面）与 Writer Room `team` 排练，且不再有重复执行逻辑。
- 并发角色子代理各自持有独立会话与事务，一个失败不污染兄弟或父会话。
- `fork` 子代理能看到父上下文的有界快照，`continuable` 能对已存在的子会话追加续跑。
- 工具目录在「未变更工具集 + 未变更顺序」下字节级稳定；计划模式不增删工具、只覆盖指令。
- 上下文压缩后仍复用同一系统提示词与工具 schema 前缀，缓存命中率可观测。
