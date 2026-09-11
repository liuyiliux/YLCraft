# 世界构建数据模型

<!-- 来源：openspec/changes/ai-progressive-world-building，导入日期：2026-09-12 -->

- **承载内容**：世界构建域 5 张表的字段语义，重点是**来源/启用状态**如何影响"AI 能看到什么、能改什么"。
- **内容来源**：`backend/app/services/novel_source/world_generation.py`、`world_domains.py`、`backend/app/db/models/novel_source.py`。
- **对 Agent 的意义**：避免在扩展世界构建能力时新建第二套运行/候选表；判断某状态该落在定义表还是候选表。
- **加载建议**：涉及世界设定、域定义、三档生成动作、候选来源时读取。

## 1. `world_domain_definitions`（项目级域定义）

| 字段 | 语义 |
|---|---|
| `project_id` / `domain_key` | 归属项目与域标识 |
| `source` | `builtin_override`（覆盖内置域）/ `custom`（用户自定义）/ `ai_suggested`（AI 建议，默认**不启用**） |
| `is_enabled` | 是否参与 `WorldDomainService.resolve_specs`；`ai_suggested` 落库时为 `False` |
| `attributes_json` | 域属性契约（内置字段**只可追加不可删除**，保证历史数据可解析） |

`resolve_specs(project_id)` 是**唯一**的域契约来源：内置域（可覆盖 label / 追加字段 / 禁用）+ 自定义域（`ai_suggested` 默认排除）。生成与提取共用它。

## 2. `world_building_templates`（世界构建模板）

| 字段 | 语义 |
|---|---|
| `project_id` | **为空即内置种子模板**；非空为项目模板 |
| `layers_json` | 层次策略（如 `世界 → 国家 → 城市 → 地点`） |
| `prompts_json` | 三档提示词 `draft_world` / `expand_domain` / `expand_entity`，支持 `{layers}`/`{domain}`/`{hint}` 等占位 |
| `is_default` / `is_builtin` | 默认模板与内置标记 |

## 3. `world_extraction_runs`（运行记录，生成与提取**共用**）

- `kind`：`extract`（提取）/ `generate`（生成）——**不新建生成运行表**
- `snapshot_id`：**可空**（生成运行无来源快照；迁移 040，downgrade 有保护）
- 复用既有 `domains_json` / `checkpoint_json` / `trace_json` / `diagnostics_json` / `status`（含 `partial` 局部失败语义）

## 4. `world_fact_candidates`（候选，生成与提取**共用**）

- `origin`：`original` / `outline` / `ai_draft` / `ai_inferred`
- `ai_draft` 的 `evidence_json="[]"`——**不得伪造证据**
- 幂等：`fingerprint = gen:{project_id}:{entity.id}`

## 5. `world_domain_suggestion_ignores`（迁移 041）

记录被忽略的域建议，避免同一建议反复提示。

## 6. 边界速查

| 想做什么 | 落哪里 |
|---|---|
| AI 建议新域/新字段 | `world_domain_definitions`，`source=ai_suggested`、`is_enabled=False`（过闸） |
| 用户确认建议 | 经 `PUT /world-domains/{key}` 转 `custom` + `is_enabled=true`（OQ-C 结论：不新增专用端点） |
| 生成的实体字段值 | `world_fact_candidates`，`origin=ai_draft` |
| 写入正典 | **只能**经 `POST /world-extraction-runs/{id}/apply` |
