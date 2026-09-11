# context-bootstrap 报告（document-ingest）

- 日期：2026-09-11
- 模式：`document-ingest`（把 `context-harvest` 产出的知识消化进 `.ai-sdd/context/`）
- 目标工作区：`F:/PycharmProjects/YLCraft`
- 触发来源：`context-harvest`（`task-observability-diagnostics` → `.ai-sdd/requirements/task-observability-diagnostics/harvest-2026-09-11.md`）

## 前置检查

| 检查项 | 结果 | 说明 |
|---|---|---|
| 目标 `.ai-sdd/context/` | **不存在** | 本次为**从零建库**，非增量合并 |
| `project-profile.yaml` | 不存在 | 无多仓 profile；YLCraft 为单仓（FastAPI + React），scope 统一用 `all` |
| `openspec/config.yaml` | 存在但为默认模板（无 `context` / `rules` 段） | 无需做 index ↔ config 双向同步 |
| `context-index.yaml` | 不存在 | 本次新建 |
| 官方模板 | `sdd-distribute-assets/.../templates/context/` | **未直接套用**：模板面向多仓 CRM（BSV/PSV/AppFrame2/CSF/ET），与本项目技术栈不匹配，套用会写入大量无关条目（违反"证据优先、不臆造"门禁） |
| GitNexus | 未初始化（无 `.gitnexus`） | 事实证据改用源码 `文件:行号` 与 change artifacts（A 级） |

## 模式输入与分析摘要

| 维度 | 输入/证据 | 发现 | 处理策略 |
|---|---|---|---|
| 文档来源 | harvest 报告（7 类知识） | 术语/规则/表/枚举/工程约束/决策，均有源码或 artifact 证据 | 按分类落到 4 个目录、7 个文件 |
| 项目身份 | 源码 + 架构文档 | 单仓 fullstack；已有权威架构文档 | context 只保留**可复用规则与约定**，叙述性内容指向架构文档，避免重复 |
| 模板适配 | 官方模板条目 | 大量条目（BSV/CSF/AppFrame2 等）在本项目不存在 | 只采用目录分类与 index 字段规范，条目全部按本项目重写 |

## GitNexus 查询效果

| 查询 | 结果 | 降级/核对动作 |
|---|---|---|
| `detect_changes` / `impact` | 不可用（GitNexus 未初始化） | 降级为源码 `文件:行号` + `rg` 符号检索 + change artifacts（符合技能降级顺序） |

## 本次生成/修改的上下文

| 类型 | 路径 | 变更摘要 | 证据来源 | 可信度 |
|---|---|---|---|---|
| 索引 | `context/context-index.yaml` | 新建：注册 7 条目（business×2、data×2、engineering×2、system×1），含 scope/stage/load_policy/triggers | 本项目实际文件结构 | A |
| 说明 | `context/README.md` | 新建：加载规则、文件清单、与架构文档的关系、证据要求 | 技能规范 | A |
| 业务 | `business/领域术语与业务对象（domain-glossary）.md` | 任务账本、三层观测视图、诊断字段、事件收口、业务语义事件、重发 vs 重试、状态级取消 | harvest §1 + 源码行号 | A |
| 业务 | `business/业务规则与核验体系（business-rules）.md` | 任务持久化双条件与白名单、启动对账、重试/重发边界、事件脱敏与截断、常见误用防呆 | harvest §2 + `task_persistence.py` / `task_queue.py` / `logs.py` | A |
| 数据 | `data/核心数据模型（data-model）/README.md` + `概览与实体关系（summary）.md` | 五张表分工与关键字段、provider id 不进主键、可重放参数唯一位置、双日志分工、重发追溯链 | harvest §4 + `db/models/task.py` | A |
| 数据 | `data/枚举值字典（enum-dictionary）.md` | 16 个 scene、两套任务白名单、状态与级别枚举、3D kind、水印操作枚举 | harvest §5 + 全量 `record_event` 扫描 | A |
| 工程 | `engineering/设计约束（design-conventions）.md` | AI 调用收口与 context 注入、任务不能自动收口、重试复用端点、`external_key=None` 坑、枚举同步、preview 截断、文档同步协议 | harvest §6 + 本轮实现 | A |
| 工程 | `engineering/接口设计规范（api-style-guide）.md` | 前缀/落点/模型/错误语义约定、任务与日志接口清单、API surface 生成流程 | 现有路由 + `tools/generate_api_surface.py` | A |
| 系统 | `system/系统交互关系与调用链（integration-map）.md` | AI 调用链路 Mermaid、两条恢复路径、任务中心聚合来源、前端入口 | harvest §7 + 实现 | A |

## 子技能输出

| 模式 | 子技能 | 子技能输出 | 合并到的正式 context | 待确认 |
|---|---|---|---|---|
| document-ingest | `context-update`（规则采用） | 合并策略（证据分级、按分类合并、index 同步、目录型 README） | 上表 7 个文件 + index + README | 无 |

注：本次未逐文件循环委托，而是按 `context-update` 的合并规则一次性消化 harvest 报告（单一文档来源）。

## 未写入正式 context 的候选内容

| 内容 | 原因 | 建议 |
|---|---|---|
| 架构文档叙述性内容（模块清单、迁移编号、部署拓扑） | 已有权威文件，写入会重复且易过期 | 需要时读 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` |
| change 专属约束（本 change 的 Phase 划分、验收细节） | 仅对当前 change 有意义 | 随 change 归档，不上升为通用 |
| 官方模板中的多仓条目（BSV/PSV/CSF/AppFrame2/ET 等） | 本项目不存在对应实体 | 若未来引入多仓，再按 profile 初始化 |
| 具体供应商 base_url / 密钥 / 连接器名称 | 属 X 级（敏感或环境特定） | 不写入 context |

## 需要人工补充或确认

| 问题 | 影响 | 建议补充方式 |
|---|---|---|
| `scope` 目前统一为 `all`（单仓 fullstack） | 若未来拆分为多仓，需要按仓库重新划分 scope | 引入 profile 后重跑 `code-discover` / `architecture-scan` |
| 尚未做 `scenario-mining`（设计手册/代码模式） | 缺少"典型需求端到端套路"沉淀 | 后续可按需跑 `context-bootstrap --mode scenario-mining` |
| 尚未做 `architecture-scan` 合并 | context/system 目前只有调用链条目 | 需要系统全景时跑 `architecture-scan` |
