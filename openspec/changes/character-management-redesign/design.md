# 角色管理设计优化 — 设计文档

## 1. 信息架构

### 1.1 角色列表 → "角色册"视图

当前：卡片墙（缩略图 + 名称 + 一行描述 + 标签）。

目标：紧凑的"角色册"卡片，保留搜索/筛选但提升信息密度：

```
┌──────────────────────────────────────┐
│  [立绘缩略图]  角色名      [定位Tag]  │
│              性别 · 年龄 · 组织       │
│  完善度: ██████░░ 6/10   [冻结]      │
│  标签: [仙侠] [剑修] [主角]          │
└──────────────────────────────────────┘
```

- 卡片增加 `bible_completion` 计算（identity/motivation/speech/behavior/ability/arc 各 1 分 + appearance/personality/background 各 1 分，共 9 分）。
- 未设置关键字段的角色用虚线边框 + 低饱和底色提示。
- 悬停卡片显示快速预览（前 3 个 Bible 字段摘要）。

### 1.2 详情视图 → 双栏布局

当前：860px Drawer + 垂直堆叠。

目标：角色详情作为独立路由 `/characters/:id` 或大 Drawer（≥ 1200px），双栏布局：

```
┌──────────────────────────┬───────────────┐
│  设定图/立绘 + 关键信息    │   Bible 分区    │
│  (左栏 ~1fr)              │   (右栏 480px)  │
│  - 立绘预览               │   - 身份        │
│  - 三视图(如有)            │   - 动机        │
│  - 关系图谱入口            │   - 语言/OOC    │
│  - 完善度指示              │   - 能力/弧光   │
├──────────────────────────┴───────────────┤
│  Prompt 资产包（折叠）                    │
│  - 出图提示词 / 设定图提示词 / 音色提示词  │
│  - 角色 JSON 导出                         │
├──────────────────────────────────────────┤
│  原文依据/来源标记区                       │
└──────────────────────────────────────────┘
```

- 断点：1240px 以下左右栏塌单栏（参考 report.html 的 `.upper` 断点）。
- 左栏包含角色设定图或立绘 + 身份标签 + 完善度。
- 右栏是 Bible 分区（保留现有 `CharacterBibleQuickPanels` + `CharacterBibleDetailedPanels` 内容，但改为更紧凑的网格）。

### 1.3 关系图谱

新增角色关系建模 + 全景视图：

- **数据模型**：`CharacterRelationship` 表

```python
class CharacterRelationship(SQLModel, table=True):
    __tablename__ = "character_relationships"
    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    character_id: str = Field(index=True)
    related_character_id: str = Field(index=True)
    relation_type: str = Field(default="")  # 师徒/恋人/兄弟/敌人...
    relation_note: str = Field(default="")   # 关系描述
    source: str = Field(default="")          # 原文/素材来源
    is_directed: bool = Field(default=False) # 单向还是双向
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

- **图谱视图**：内联 SVG 圆环布局（参考 report.html 的关系图谱），不引 d3。
  - 节点按 `role`（主角实心、配角空心、路人小点）。
  - 弦是贝塞尔曲线，悬停高亮 + 点击跳转。
  - 关系文字沿弦错位显示（`t = 0.5 + ((i%3)-1)*0.14`）。
  - 进入图谱模式时与角色详情互斥。

- **入口**：角色管理页顶部 Tab 增加"关系图谱"，角色详情内也有"查看关系"按钮跳转到图谱并聚焦该角色。

### 1.4 角色设定图生成预设

在现有 `PORTRAIT_PRESET_OPTIONS` 中新增 `character_sheet_16_9`：

- 16:9 横构图，左侧约 34% 半身像（面部基准），右侧上半三视图（正视/侧视/背视），右下关键细节条。
- 提示词模板参考参考仓库的 `sheet.md` 约束：
  - 白底、分区光照（左栏方向光、右侧平光）。
  - 面部一致性：左右必须同一个人。
  - 比例正确：不拉伸、不压扁。
  - 细节条让位给三视图，不反过来。
- 生成结果入 Asset Hub（复用现有 `portrait/generate` 链路），作为角色 `portrait_node_id` 的子节点或独立 Node。

### 1.5 字段来源标记

- 在 `Character` 上增加 `field_sources_json`（JSON 对象，`{"appearance": "original|ai_inferred", "personality": "original", ...}`）。
- 前端 Bible 字段旁显示来源徽标：`原文`（铁锈红/绿） vs `AI 推断`（橙色） vs `未设置`（灰）。
- 参考 report.html 的 `（推断）` 视觉处理：浅铁锈红底 + 小号字。

### 1.6 Prompt 资产包

角色详情底部新增可折叠面板：

| 面板 | 内容 | 复制按钮 |
|---|---|---|
| 出图提示词 | 主立绘提示词 + 反向提示词 | 2 |
| 设定图提示词 | `character_sheet_16_9` 预设的完整提示词 | 1 |
| 音色提示词 | 基于 speech 字段生成的 TTS 提示词 | 1 |
| 角色 JSON | 完整角色数据（identity/motivation/.../appearance 等） | 1 |

## 2. 后端接口变更

### 2.1 新增接口

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/characters/{character_id}/relationships` | 列出角色关系 |
| POST | `/api/v1/characters/{character_id}/relationships` | 创建关系 |
| PUT | `/api/v1/characters/{character_id}/relationships/{rel_id}` | 更新关系 |
| DELETE | `/api/v1/characters/{character_id}/relationships/{rel_id}` | 删除关系 |
| GET | `/api/v1/characters/relationships/graph` | 获取全量角色关系图谱数据 |
| GET | `/api/v1/characters/{character_id}/prompt-pack` | 生成角色 Prompt 资产包（出图/音色/JSON） |

### 2.2 新增字段

`Character` 表增加 `field_sources_json`（text，默认 `{}`）。

### 2.3 Alembic 迁移

- `024_add_character_field_sources` — 新增 `field_sources_json` 字段。
- `025_add_character_relationships` — 新增 `character_relationships` 表。

## 3. 前端组件结构

```
frontend/src/pages/characters/
├── index.tsx                 # 入口（列表 + 筛选 + 分页）
├── CharacterRosterCard.tsx   # 角色册卡片（含完善度指示器）
├── CharacterDetail.tsx       # 双栏详情视图
├── CharacterRelationshipGraph.tsx  # 关系图谱（内联 SVG）
├── CharacterPromptPack.tsx   # Prompt 资产包面板
└── character-bible/          # Bible 分区组件（重构现有 QuickPanels/DetailedPanels）
    ├── IdentityPanel.tsx
    ├── MotivationPanel.tsx
    └── ...
```

## 4. 视觉设计原则

参考 `shuohao-skills/novel-characters/references/report-style.md`：

1. **双字域**：角色名/书名/原文引文用宋体（叙事语域），Bible 字段/标签/界面用黑体（分析语域），英文 prompt/序号用等宽字体。
2. **颜色纪律**：冷灰印张 + 铁锈红印记。红色只用在原文引文、主角标签和当前选中态。角色来源类型保留现有彩色标签（不统一成灰色）。
3. **屏幕上收、纸上全展开**：详情一次只看一个角色，长面板折叠在 `<details>`/`Collapse` 里，可展开。
4. **推断标记高亮**：`（推断）`/`(inferred)` 自动包成带浅铁锈红底的徽标，半角/全角 × 中英四种写法都认。
5. **自包含**：不引外部字体或图库。

## 5. 分阶段实施

### Phase 1: 数据与接口基础
- 新增 `CharacterRelationship` 表 + Alembic 迁移
- 新增 `field_sources_json` 字段 + 迁移
- 新增关系 CRUD API + `prompt-pack` API

### Phase 2: 前端列表与详情改造
- 角色册卡片（完善度指示器 + 紧凑信息）
- 详情双栏布局（`/characters/:id` 独立路由或大 Drawer）
- Bible 分区重构

### Phase 3: 关系图谱
- 内联 SVG 圆环布局组件
- 关系 CRUD 表单（角色详情内 + 图谱视图）
- 图谱与详情互斥切换

### Phase 4: 设定图预设与 Prompt 资产包
- `character_sheet_16_9` 提示词模板
- Prompt 资产包面板 + 复制按钮
- 字段来源标记徽标

### Phase 5: 验证与文档
- 后端 focused 测试
- 前端构建 + 浏览器验收
- 更新 API Surface / 架构文档 / Agent Skill（如需）
