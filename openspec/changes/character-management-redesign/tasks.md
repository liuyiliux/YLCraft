# 实施计划

## Phase 1: 数据与接口基础

- [x] 1.1 新增 `CharacterRelationship` 模型（`character_id`、`related_character_id`、`relation_type`、`relation_note`、`source`、`is_directed`）+ Alembic 迁移 `025_add_character_relationships`
- [x] 1.2 `Character` 表新增 `field_sources_json` 字段（text，默认 `{}`）+ Alembic 迁移 `024_add_character_field_sources`
- [x] 1.3 新增关系 CRUD API：`GET/POST/PUT/DELETE /api/v1/characters/{id}/relationships`
- [x] 1.4 新增 `GET /api/v1/characters/relationships/graph`（全量关系图谱数据）
- [x] 1.5 新增 `GET /api/v1/characters/{id}/prompt-pack`（生成 Prompt 资产包：出图/音色/JSON/设定图）
- [x] 1.6 后端 focused 测试：关系 CRUD、字段来源标记、prompt-pack 生成（含历史数组字段归一化）

## Phase 2: 前端列表与详情改造

- [ ] 2.1 角色列表卡片升级为"角色册"视图（完善度指示器、紧凑 Bible 摘要、未完善角色视觉弱化）
- [x] 2.2 新增独立角色详情路由 `/characters/:characterId`：左侧视觉中心、中央参考图/设定图、右侧 Bible，下方关系与 Prompt 资产包；角色卡和关系图节点默认跳转独立页
- [x] 2.2A 将 `/characters` 替换为角色工作区入口：默认打开首个角色详情，角色列表/筛选固定在左侧；旧卡片列表仅作为兼容管理入口
- [x] 2.2B 当前详情页恢复立绘版本缩略图、版本切换与“设为主视图”同步逻辑（版本本地文件统一转换为浏览器可访问地址）
- [x] 2.2C 当前详情页提供直接编辑弹窗，不再要求先跳转管理页
- [x] 2.2E 当前详情页提供直接新建弹窗，创建成功后进入新角色详情
- [x] 2.2F 当前详情页支持从素材库选择图片并写回角色视觉参考图集合
- [x] 2.2G 当前详情页支持直接添加/移除世界使用记录
- [x] 2.2M 当前详情页支持编辑世界使用记录，并使用后端 PUT 更新局部设定
- [x] 2.2N 当前详情页支持关系编辑与删除
- [x] 2.2O 世界使用新增改为选择创作项目，不再要求用户手填 `story_id`
- [x] 2.2P 生图/AI 补全成功后自动刷新角色 Prompt、立绘版本与生图日志
- [x] 2.2Q 当前详情页区分主视图与参考图集合；版本卡支持预览、设为主视图、加入参考与切片，设主视图后同步角色身份基准图
- [x] 2.2R 当前详情页支持从角色直接进入已关联项目生产线，并迁移世界使用的别名、阵营、状态、局部 Prompt 标签、OOC/出模约束与 Bible/视觉覆盖
- [x] 2.2S 当前详情页支持选择 LLM 补全供应商/模型、负面提示词与生图 Prompt 预览，并将参数写入角色生图请求
- [x] 2.2T 当前详情页将生图日志按状态/供应商/模型/时间展示，并将切片记录改为可预览缩略图
- [x] 2.2U 支持从角色详情“以此角色新建项目”，预填项目创意并在创建后自动关联角色与项目
- [x] 2.2V 角色库为空时进入 `/characters/new` 新工作区创建弹窗，创建后进入真实角色详情，不再依赖旧管理页
- [x] 2.2W 参考图选择弹窗补齐素材库搜索，并按素材库图片/历史立绘版本分组
- [x] 2.2X 当前详情页支持移除单张角色参考图，主视图需通过版本切换避免误删
- [x] 2.2Y 当前详情页支持在选定 LLM 下优化角色生图 Prompt，结果仅回填待确认输入框
- [x] 2.2Z 当前详情页恢复旧版本详情：版本可独立预览，展开查看 Prompt、负面 Prompt、生成参数，并明确区分当前主视图与参考图集合
- [x] 2.2AA 新建/编辑统一在新角色工作区当前页弹窗完成；旧 `/characters/manage` 路由仅兼容重定向到新工作区
- [x] 2.2AB 编辑弹窗保留并可修改旧详情中的视觉 Profile（包含身份基准图与参考图字段），避免迁移后丢失角色视觉数据
- [x] 2.2AC “以此角色新建项目”创建后立即把完整角色卡写入项目大纲并建立项目关联，后续大纲/演绎/分镜/生图可直接使用，无需再次手动同步
- [x] 2.2AD 角色生图请求始终使用当前身份基准图与参考图集合，不使用临时版本预览作为隐式参考
- [x] 2.2AE Story 生产线的角色立绘生成复用角色详情中的身份基准图/参考图，并在生成后回写项目大纲角色与项目资产血缘
- [x] 2.2AF 生成故事大纲时保留项目已绑定的角色卡与视觉字段，避免角色先行项目被 LLM 返回的大纲角色覆盖
- [x] 2.2H 当前详情页接入 AI 补全缺失设定与角色主立绘生成入口
- [x] 2.2I 角色生图入口支持预设、尺寸、提示词覆盖、载入 Prompt 资产包与统一重写
- [x] 2.2J 当前详情页支持直接添加角色关系，并刷新关系列表
- [x] 2.2K 修正世界使用关联必填 `story_id`，并在当前页提供项目 ID 输入
- [x] 2.2L 当前详情页支持立绘版本生成切片，切片结果回写并保留来源血缘
- [x] 2.2D 完成世界使用、立绘版本/切片、生图日志、参考图素材选择、AI 补全/生图、标签等全部旧 Drawer 能力迁移；删除旧角色管理实现文件，`/characters/manage` 仅保留路由兼容重定向
- [ ] 2.3 Bible 分区组件重构（复用现有 `CharacterBibleQuickPanels`/`CharacterBibleDetailedPanels` 数据，改为紧凑网格）
- [x] 2.4 详情中新增字段来源徽标（原文/AI 推断/用户填写/未设置）
- [x] 2.5 前端构建 + 基础验收（`npm run build`）

## Phase 2A: 角色生产流程分类

- [x] 2A.1 明确“小说提取角色（extract）”与“角色先行再演绎（character-first）”为两类不同入口，不共享强制正文/大纲门禁
- [x] 2A.2 在角色页提供流程来源标识和切换：从小说/正文提取、独立创建角色、从素材库导入（新增 `workflow_source` 字段、元数据接口、详情标识和列表筛选）
- [x] 2A.3 角色先行流程可直接进入角色设定、参考图、关系和 Prompt 资产包，再选择性回流 Story/生产线
- [x] 2A.4 小说提取流程保留原文依据与字段来源，提取结果可转为可复用角色卡
  - 2A.4.1 `sync_outline_characters` 同步时写入 `field_sources`（外来文本 → `original`，原创大纲 → `ai_inferred`）
  - 2A.4.2 提取来源细分 `extract_origin`：`uploaded_novel` / `imported_novel` / `original_outline`，落在 `character_story_links`（迁移 `027`）
  - 2A.4.3 用户在工作区手填字段标 `user_edited`，同步流程只补空缺不覆盖已有来源
  - 2A.4.4 角色列表/详情新增提取来源筛选、标签与 `GET /api/v1/characters/meta/extract-origins` 元数据

## Phase 2B: 角色工作区视图增强

- [x] 2B.1 删除 `/characters/manage` 兼容重定向路由（旧页面已不存在，无需兜底）
- [x] 2B.2 角色工作区全屏切换（方案 B）：AppLayout 内隐藏 Header、内容区占满视口、Esc 退出、路由切换自动恢复，不新增路由
- [x] 2B.3 世界视角切换条：基准设定 + 各项目/世界 Tab，切换后展示有效 Bible、服装覆盖与视觉覆盖
- [x] 2B.4 覆盖差异提示卡：明确列出别名、阵营、本世界身份、服装覆盖、局部 Prompt 标签、OOC/出模约束与覆盖字段名

## Phase 3: 关系图谱

- [x] 3.1 内联 SVG 圆环布局关系图谱组件（不引外部图库）
- [x] 3.2 图谱交互：点击节点跳转，关系文字沿连线展示
- [x] 3.3 角色详情内关系 CRUD 表单（添加/编辑/删除关系）
- [x] 3.4 图谱与详情互斥切换（详情内入口定位到图谱区）
- [x] 3.5 角色详情迁移收藏、删除与旧立绘升级到资产中枢操作

## Phase 4: 设定图预设与 Prompt 资产包

- [x] 4.1 新增 `character_sheet_16_9` portrait 预设（提示词模板：左 34% 半身像 + 右三视图 + 细节条，白底/分区光照/面部一致性约束；保留 `identity_board_16_9` 兼容别名）
- [x] 4.2 设定图生成结果入 Asset Hub（复用现有 `portrait/generate` 链路）
- [x] 4.3 Prompt 资产包面板（出图提示词/设定图提示词/音色提示词/JSON，全部带复制按钮；默认输出中文可直接使用模板）
- [x] 4.4 字段来源标记徽标渲染（原文 / AI 推断 / 用户填写 / 本世界覆盖）

## Phase 5: 验证与文档

- [x] 5.1 后端 focused 测试（关系、prompt-pack、字段来源、项目角色先行回流与预设、提取来源细分 `tests/test_character_provenance.py`）
- [ ] 5.2 前端浏览器验收（角色册列表、独立角色页、关系图谱、Prompt 面板）
- [x] 5.3 更新 `docs/architecture/API_SURFACE.md` + `api_surface.json`
- [x] 5.4 更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`（新增关系模型与角色先行创建项目描述）
- [x] 5.5 更新本 OpenSpec 记录完成状态
