# 实施计划

## Phase 1: 数据与接口基础

- [ ] 1.1 新增 `CharacterRelationship` 模型（`character_id`、`related_character_id`、`relation_type`、`relation_note`、`source`、`is_directed`）+ Alembic 迁移 `025_add_character_relationships`
- [ ] 1.2 `Character` 表新增 `field_sources_json` 字段（text，默认 `{}`）+ Alembic 迁移 `024_add_character_field_sources`
- [ ] 1.3 新增关系 CRUD API：`GET/POST/PUT/DELETE /api/v1/characters/{id}/relationships`
- [ ] 1.4 新增 `GET /api/v1/characters/relationships/graph`（全量关系图谱数据）
- [ ] 1.5 新增 `GET /api/v1/characters/{id}/prompt-pack`（生成 Prompt 资产包：出图/音色/JSON/设定图）
- [ ] 1.6 后端 focused 测试：关系 CRUD、字段来源标记、prompt-pack 生成

## Phase 2: 前端列表与详情改造

- [ ] 2.1 角色列表卡片升级为"角色册"视图（完善度指示器、紧凑 Bible 摘要、未完善角色视觉弱化）
- [ ] 2.2 详情改为双栏布局（左栏设定图/立绘 + 关键信息，右栏 Bible 分区），断点 1240px 塌单栏
- [ ] 2.3 Bible 分区组件重构（复用现有 `CharacterBibleQuickPanels`/`CharacterBibleDetailedPanels` 数据，改为紧凑网格）
- [ ] 2.4 详情中新增字段来源徽标（原文/AI 推断/未设置）
- [ ] 2.5 前端构建 + 基础验收

## Phase 3: 关系图谱

- [ ] 3.1 内联 SVG 圆环布局关系图谱组件（不引外部图库）
- [ ] 3.2 图谱交互：悬停高亮、点击跳转、关系文字沿弦错位
- [ ] 3.3 角色详情内关系 CRUD 表单（添加/编辑/删除关系）
- [ ] 3.4 图谱与详情互斥切换（列表页 Tab + 详情内入口）

## Phase 4: 设定图预设与 Prompt 资产包

- [ ] 4.1 新增 `character_sheet_16_9` portrait 预设（提示词模板：左 34% 半身像 + 右三视图 + 细节条，白底/分区光照/面部一致性约束）
- [ ] 4.2 设定图生成结果入 Asset Hub（复用现有 `portrait/generate` 链路）
- [ ] 4.3 Prompt 资产包面板（出图提示词/设定图提示词/音色提示词/JSON，全部带复制按钮）
- [ ] 4.4 字段来源标记徽标渲染（`（推断）`/`(inferred)`/原文）

## Phase 5: 验证与文档

- [ ] 5.1 后端 focused 测试（关系、prompt-pack、字段来源）
- [ ] 5.2 前端浏览器验收（角色册列表、双栏详情、关系图谱、Prompt 面板）
- [ ] 5.3 更新 `docs/architecture/API_SURFACE.md` + `api_surface.json`
- [ ] 5.4 更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`（新增关系模型描述）
- [ ] 5.5 更新本 OpenSpec 记录完成状态
