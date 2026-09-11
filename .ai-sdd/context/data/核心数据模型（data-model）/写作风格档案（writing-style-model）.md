# 写作风格档案数据模型

<!-- 来源：openspec/changes/creative-writing-style-profiles（design.md「Profile shape」）与 backend/app/db/models/creative_project.py，导入日期：2026-09-11 -->

- **承载内容**：写作风格域两张表（档案本体 / 项目绑定）的字段语义，以及"绑定不复制内容"的边界。
- **内容来源**：`backend/app/db/models/creative_project.py` 的 `WritingStyleProfile`（`:522`）与 `ProjectWritingStyleLink`（`:498`）。
- **对 Agent 的意义**：判断风格相关状态与参数该落档案表还是绑定表；避免误以为绑定会改写项目字段；避免用错列名。
- **加载建议**：处理写作风格、风格绑定、T6 注入、归档/取消归档相关需求时读取。

## 1. `writing_style_profiles`（风格档案本体）

| 字段 | 含义 |
|---|---|
| `id` | 主键 |
| `owner_id` | 归属者（默认 `default`） |
| `name` / `description` | 展示信息 |
| `source_type` | `user_defined` / `extracted_from_source` / `agent_draft` / `builtin` |
| `source_snapshot_id` / `source_sample_hash` | 来源快照与样本哈希；**不落来源正文、不存原句** |
| `status` | `draft` / `reviewed` / `active` / `archived`（默认 `draft`） |
| `version` | 版本号（默认 1）；生成时记录所用版本 |
| `profile_json` | 表达机制维度（每维 `value` / `confidence` / `evidence_summary` / 可选 `measurement_keys`） |
| `prompt_contract_json` | 有界可注入契约：`rules`（上限 40）/ `new_examples` / `prohibited_source_material` |
| `provenance_json` | 溯源与材料检查结果（来源专名、违规/告警判定） |
| `checksum` | 内容校验和；与 `version` 一起进 T6 与生成日志，保证"用了哪一版"可审计 |
| `created_at` / `updated_at` | 时间戳 |

索引：`(owner_id, status)`、`(source_snapshot_id, source_sample_hash)`。

## 2. `project_writing_style_links`（项目绑定 = 运行时选择）

| 字段 | 含义 |
|---|---|
| `id` | 主键 |
| `project_id` | 外键 → `creative_projects.id` |
| `style_profile_id` | 外键 → `writing_style_profiles.id` |
| `enabled` | 是否启用（默认 `true`） |
| `priority` | 优先级（默认 100；生效中的排前面） |
| `intensity` | `subtle` / `balanced` / `strong`（默认 `balanced`），决定**注入力度**（规则 8/16/24、示例 1/2/4） |
| `stage_scope_json` | 生效阶段范围（JSON 数组，如 `["novel_body"]`） |
| `dimension_overrides_json` | 项目级维度覆盖（JSON 对象） |
| `created_at` / `updated_at` | 时间戳 |

索引：唯一索引 `(project_id, style_profile_id)`、运行时索引 `(project_id, enabled, priority)`。

## 3. 边界（易错）

- **绑定不复制内容**：档案内容永不写入项目的 `outline_json` / `settings_json` 等字段，绑定只是运行时关联。
- **归档不解绑**：档案归档后绑定记录保留，但运行时不再返回它（自动失效）；取消归档回到草稿后，也需重新审核 + 激活才生效。
- **档案 ≠ 测量**：`ProjectStyleMeasurement` 是某正文版本的观测证据，**不可直接当提示词**；只有档案的 `prompt_contract_json` 能进 T6。
- **列名易错**：绑定表用的是 `stage_scope_json` / `dimension_overrides_json`，**没有** `stage_scope` / `override_json` 这两个列名。
