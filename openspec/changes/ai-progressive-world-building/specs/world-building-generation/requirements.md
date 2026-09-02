# Requirements: AI Progressive World Building

> 全部需求服从 proposal 的**梯子原则**（I1 平台持有梯子 / I2 AI 只能踩梯子上加 / I3 平台永远能解析）。
> 编号 R1-R8；每条需求用 WHEN/THEN 场景描述可验收行为。

## R1: 从想法生成世界骨架

系统 SHALL 支持从「一个想法或大纲」生成多域世界骨架，产出结构化候选而非散文。

### Scenario: 用一句话生成骨架

- **WHEN** 用户提供项目想法（如「赛博朋克都市里的义体侦探」）并请求生成世界骨架
- **THEN** 系统 SHALL 按项目已启用的域清单生成各域的粗略候选
- **AND** SHALL 把每条候选落到对应域的 `attributes` 字段上（结构化，非自由文本）
- **AND** SHALL 标记 `origin=ai_draft`（无原文证据）
- **AND** SHALL 支持生成前预览提示词，不消耗模型配额

### Scenario: 骨架生成本身也建议结构

- **WHEN** 生成过程中模型识别出内置 schema 无法承载的维度（如「义体改造等级」）
- **THEN** 系统 SHALL 将其作为**建议字段/建议域**单独列出
- **AND** SHALL 在用户确认前不参与提取、不写入正典

## R2: 域级细化

系统 SHALL 支持对指定域做整体细化，并按可配置的层次策略组织。

### Scenario: 按层次策略细化地点域

- **WHEN** 用户对「地点」域请求细化，并选定层次策略（如 `世界 → 国家 → 城市 → 地点`）
- **THEN** 系统 SHALL 按该层次生成/补齐各层级的条目
- **AND** SHALL 保留层级归属关系（供地图区域层级与导出使用）
- **AND** SHALL 复用该域的 `attributes` schema 填充各条目字段

## R3: 实体属性补充

系统 SHALL 支持对单个实体按域 schema 逐字段补充属性。

### Scenario: 补齐一个地点的缺失字段

- **WHEN** 用户选中一个地点实体并请求补充属性
- **THEN** 系统 SHALL 按该域的字段清单标出「已填 / 缺失」
- **AND** SHALL 允许用户只勾选部分字段让 AI 补充
- **AND** SHALL 只回写用户勾选并确认的字段，不覆盖已有内容

## R4: 提示词可编辑与预览

系统 SHALL 让每一档生成动作的提示词可见、可编辑、可预览后再执行。

### Scenario: 编辑并预览提示词

- **WHEN** 用户发起任一生成动作
- **THEN** 系统 SHALL 展示本次将使用的完整提示词
- **AND** SHALL 允许用户编辑（项目级保存为模板，或单次覆盖）
- **AND** SHALL 在真正调用模型前提供预览入口，预览不消耗配额

## R5: 世界构建模板

系统 SHALL 提供项目级世界构建模板：层次策略 + 每档默认提示词。

### Scenario: 定义项目层次策略

- **WHEN** 用户在项目设置中编辑世界构建模板
- **THEN** 系统 SHALL 允许定义或替换层次策略（层级数量与名称由项目决定）
- **AND** SHALL 允许为每档配置默认提示词
- **AND** SHALL 提供内置模板（洋葱模型 / 地理层级 / 势力剧构等）作为起点，可复制后改

## R6: 生成与提取的语义隔离

系统 SHALL 明确区分「从原文提取」与「AI 生成」两类内容，且不得互相伪装。

### Scenario: 无原文的生成内容

- **WHEN** 一条候选来自生成链路（没有原文可引用）
- **THEN** 系统 SHALL 标记 `origin=ai_draft`
- **AND** SHALL 不为其伪造证据锚点
- **AND** SHALL 在 UI 上与 `original`（原文可考）视觉区分

### Scenario: 生成内容写入正典

- **WHEN** 用户确认一条 `ai_draft` 候选并 apply
- **THEN** 系统 SHALL 写入时保留 `ai_draft` 来源标记
- **AND** SHALL 沿用既有唯一写入点，不新增写入通道

## R7: 结构扩充需过闸

系统 SHALL 保证 AI 对结构的任何变更都必须经用户确认才成为 schema。

### Scenario: 确认 AI 建议的字段

- **WHEN** AI 建议为某域追加字段，用户确认
- **THEN** 系统 SHALL 将该字段写入项目级定义（`source` 由 `ai_suggested` 转 `custom` 并启用）
- **AND** SHALL 保证内置字段不被删除（既有 `attributes_json` 始终可解析）

### Scenario: 确认 AI 建议的新域

- **WHEN** AI 建议新增一个内置域之外的模块，用户确认
- **THEN** 系统 SHALL 落为自定义域，实体写入 `world_entities`（`entity_type` 取定义值）
- **AND** SHALL 使该域可参与后续提取与生成

## R8: 可解析性保证

系统 SHALL 保证无论 AI 如何扩充，世界数据始终可列出、可检索、可导出、可对比。

### Scenario: 导出含自定义字段的世界

- **WHEN** 用户导出一个包含自定义域与自定义字段的项目
- **THEN** 导出结构 SHALL 同时包含域定义（`layers`/域清单）与实体属性
- **AND** SHALL 保证未知字段原样保留，不因 schema 演进而丢失

### Scenario: 读取旧数据

- **WHEN** 系统读取在旧 schema 下写入的 `attributes_json`
- **THEN** SHALL 仍能解析出全部内置字段
- **AND** 缺失的新字段按空处理，不报错
