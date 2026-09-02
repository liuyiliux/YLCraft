# Implementation Plan

> 前置：任务 21.5（世界模块与属性可扩展底座）已完成——`world_domain_definitions` 表（迁移 038）、
> `WorldDomainService`、三个域定义端点，以及 religion/language/culture/ecology 四个内置模块。
> 本 change 在此梯子上实现「AI 渐进生成」。
>
> **双使用者约束（贯穿所有任务）**：每个能力必须同时交付**真人页面入口**与**智能体 Skill/API 入口**，
> 两者共用同一服务层、同一契约、同一「先预览后确认」纪律；缺一个入口不算完成。

## Phase 0: Contracts and product decisions

- [x] 1. Freeze the generation run contract and origin semantics.
  - Decide whether generation runs reuse `WorldExtractionRun` with a `kind` field or add a separate table.
  - Add `ai_draft` to candidate origin semantics; forbid fabricated evidence for generated items.
  - _Requirement: R6_
  - _Decision: D-3（复用 WorldExtractionRun 加 kind，不新建运行表）_
  - _Done: `ExtractionRunKind`（extract/generate）+ `WorldExtractionRun.kind` 字段（迁移 `039`，既有行默认 `extract`，索引 `ix_world_extraction_runs_kind`）；`CandidateOrigin` 新增 `AI_DRAFT`，docstring 明确「生成链路不得伪造证据锚点、UI 需与 original 区分」。测试锁住默认 `kind=extract`。_
- [x] 2. Define the world building template schema and storage.
  - Templates carry layer strategy (names/count are project-defined) plus per-action prompts.
  - _Requirement: R4, R5_
  - _Decision: D-1（新建 world_building_templates 表）_
  - _Done: `WorldBuildingTemplate`（迁移 `039`）：`layers_json` 存层次策略、`prompts_json` 存三档提示词模板（支持 `{layers}`/`{domain}`/`{entity}`/`{fields}` 占位），`project_id` 为空即内置种子模板，`is_default`/`is_builtin` 区分项目默认与内置只读。层次名称与层数完全由数据决定，代码中不存任何枚举。测试锁住「层次由数据决定」。_
- [ ] 3. Define the structured suggestion contract.
  - `suggested_fields` / `suggested_domains` are returned separately from content and never applied automatically.
  - _Requirement: R1, R7_

## Phase 1: Generation service

- [ ] 4. Add `expand_entity`: fill selected fields of one entity by its domain schema.
  - Only write back fields the user selected and confirmed; never overwrite filled values.
  - _Requirement: R3_
  - _Decision: D-4（不直接改正典，一律先候选再确认）_
- [ ] 5. Add `draft_world`: turn an idea/outline into a multi-domain skeleton.
  - Limit domains and item count by default; return structure suggestions separately.
  - _Requirement: R1_
  - _Decision: D-2（默认基础层 + 模板指定域）_
- [ ] 6. Add `expand_domain`: refine one domain following the template layer strategy.
  - Preserve layer membership so map regions and exports stay usable.
  - _Requirement: R2_

## Phase 2: Prompts and review

- [ ] 7. Add editable project-level templates with built-in starters.
  - Onion model, geographic hierarchy, faction-driven, seven-layer worldbuilding.
  - _Requirement: R5_
- [ ] 8. Add `prompt-preview` for every generation action.
  - Preview must not consume model quota; single-run override vs save-as-template.
  - _Requirement: R4_
- [ ] 9. Route generated candidates through the existing review and apply pipeline.
  - Surface `ai_draft` origin in lists, detail and export; never merge it silently with sourced facts.
  - _Requirement: R6_

## Phase 3: Structure suggestions

- [ ] 10. Persist AI-suggested fields/domains as `source=ai_suggested`, disabled by default.
  - Confirmation converts them to `custom` and enables them; built-in fields stay undeletable.
  - _Requirement: R7_
- [ ] 11. Show custom domains/fields with source and enablement state; support disable and reset.
  - _Requirement: R7_

## Phase 4: Compatibility, validation and rollout

- [ ] 12. Guarantee parseability across schema evolution.
  - Unknown fields are preserved as-is; old `attributes_json` always parses with built-in fields.
  - Exports include domain definitions alongside entity attributes.
  - _Requirement: R8_
- [ ] 13. Reuse reconciliation and contradiction detection as the post-generation review step.
  - _Requirement: R1, R6_
- [ ] 14. Add tests for the three actions, prompt preview, suggestion gating, origin marking and parseability.
  - _Requirement: R1, R3, R4, R7, R8_
- [ ] 15. Update API surface, architecture docs and Agent tool documentation.
  - _Requirement: R1, R4_
- [ ] 16. Add Agent tools for the three generation actions, mirroring the human flow.
  - _Requirement: R1, R3_
