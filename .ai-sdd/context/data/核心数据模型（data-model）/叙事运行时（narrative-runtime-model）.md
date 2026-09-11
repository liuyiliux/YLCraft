# 叙事运行时数据模型

<!-- 来源：openspec/changes/creative-project-narrative-runtime，导入日期：2026-09-12 -->

- **承载内容**：叙事运行时四张表的字段语义、溯源设计与"谁能进生成上下文"的分界。
- **内容来源**：`openspec/changes/creative-project-narrative-runtime/design.md`（Data Model / Canon Rules）。
- **对 Agent 的意义**：判断某份数据是"正典 / 有界状态 / 软状态 / 提案"，从而决定它能否进入生成上下文。
- **加载建议**：涉及章节产出后的状态派生、伏笔台账、叙事图谱、上下文分层时读取。

## 四张表

| 表 | 承载 |
|---|---|
| `ProjectNarrativeSnapshot` | 每个已批准正文版本一份**当前**快照，历史保留 |
| `ProjectStoryEvent` | 归一化事件（类型/参与者/地点/时间线序/章节溯源/证据锚点） |
| `ProjectForeshadowing` | 伏笔台账 |
| `ProjectStyleMeasurement` | 风格测量（篇幅/对话占比/句法节奏/张力/声线相似度） |

另有 `ProjectNarrativeRun` 承载手动/批次/自动驾驶的运行状态（沿用既有任务与 trace 约定，**不新建第二个通用 runtime**）。

## 关键字段

- `source_content_id` / `source_version` / `chapter_number` / 源指纹 / 抽取与运行溯源：**快照、事件、台账行始终携带**
- `context_fingerprint`：上下文包的指纹，可检视、可复核
- `ProjectForeshadowing.expected_window{start,end}` / `evidence_anchor{paragraph_index}`：伏笔的预期窗口与证据定位

## 谁能进生成上下文（最重要的一张表）

| 状态 | 来源 | 可入生成上下文 | 可否自动改变 |
|---|---|---|---|
| `novel_body` | 人工 promote 的章节版本 | 是 | **否** |
| 锁定的 `project_bible` / `world_asset` | 用户确认的事实 | 是，**硬约束** | **否** |
| `ProjectNarrativeSnapshot` | 已批准正文的 aftermath | 是，有界状态 | **仅**由源版本重放 |
| `ProjectStoryEvent` / `ProjectForeshadowing` | 已批准正文抽取 | 是，按审阅策略作软状态 | **仅**显式动作或确定性重放 |
| `ProjectContinuityCandidate` | 审阅/抽取提案 | **否** | 仅待决 |
| Writer Room 候选 | 模型输出 | **否**（除非作为显式当前输入） | 否 |
| Canvas / 资产 / Agent 线程数据 | 外部流程数据 | **否**（除非显式关联并 promote） | 否 |

**幂等键**：`source_content_id + source_fingerprint + pipeline_version`。
**取代语义**：新的已批准正文版本**取代**旧版派生状态（`superseded`），但**不销毁**旧状态。
