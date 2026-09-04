# 规格 · 区域几何（region-geometry）

> 需求来源：`.ai-sdd/requirements/region-geometry-rework/discover-2026-09-04.md`（状态：已确认）
> 样式基线：`docs/design/world-map-workbench-style.md`；参考调研：`docs/design/fantasy-map-generator-reference.md`

## 1. 数据模型

### 1.1 区域（WorldMapRegion）

```jsonc
{
  "id": "r1",
  "name": "徐家村",
  "kind": "村落",
  "parent_id": null,              // 新增：父区域，null 为顶层（不限层嵌套）
  "shape": {                      // 新增：独立几何（缺失时回退 auto 生成，见 1.3）
    "mode": "auto",               // auto = 参数驱动可重算；manual = 顶点已固化
    "seed": 817,                  // 整数，保证同参数同结果
    "params": {
      "nature": "河谷",            // 自然意象 8：平原/森林/山地/丘陵/湿地/荒漠/河谷/海岸
      "settlement": "沿河狭长",     // 聚落形态 6：圆形寨子/带状街区/散点村落/环山聚落/方形城邑/沿河狭长
      "structure": "港口半岛",      // 人工构筑 3+：城墙方形/要塞星形/港口半岛（可扩展）
      "scale": "中",               // 面积感：小/中/大
      "irregularity": 0.4          // 不规则度 0~1
    },
    "vertices": [[x, y], "..."]    // ≤64 个 0-100 坐标；auto 模式由算法展开，manual 为用户编辑结果
  }
}
```

- 旧字段（`name` / `kind` / 描述等）保留不变，改动为**纯增量**。
- `vertices` 为空数组 = 尚未生成形状。

### 1.2 据点（WorldMapNode）

**结构不变**（`region_id` 仍是唯一归属依据）：

- 据点落在形状外 → 画布与详情面板给 `--p-warn` 提示条，**不自动改 `region_id`**；
- 不做 point-in-polygon 自动归属（避免隐式数据变更）。

### 1.3 兼容与回退

- 本次清库后不存在旧几何；但渲染端仍要健壮：**区域无 `vertices` 时，按成员据点 + 默认参数
  （`seed = hash(region.id)`）在内存中生成一次 auto 形状用于显示**，不写库。

## 2. 形状展开算法（前端纯函数 · 可单测）

文件：`frontend/src/utils/regionShape.ts`（新），导出：

```ts
export interface RegionShapeParams {
  nature: NatureImagery
  settlement: SettlementForm
  structure?: StructureForm
  scale: '小' | '中' | '大'
  irregularity: number      // 0~1
}
export function expandRegionShape(
  points: { x: number; y: number }[],   // 成员据点（可为空）
  params: RegionShapeParams,
  seed: number,
): [number, number][]                   // ≤64 个顶点，闭合由渲染端处理
```

**流程（确定性，无随机源除 seed 外）**：

1. **骨架**：无据点时以画布中心 + 默认半径起形；有据点时取质心与离散度决定中心与基础半径 `r`（据 scale 缩放）。
2. **基础多边形**：按 `settlement` 给出角度与半径分布
   - 圆形寨子：均匀角度
   - 带状街区：长宽比 ≈ 3:1
   - 散点村落：多峰（2-3 个聚集核）
   - 环山聚落：环形 + 一侧缺口
   - 方形城邑：四边形 + 圆角
   - 沿河狭长：长宽比 ≥ 5:1 且沿主轴
3. **自然意象修正**：`nature` 调整粗糙度、凹入强度、边缘硬度
   - 山地/丘陵：高粗糙度、硬边；湿地/海岸：一侧平直、破碎感；平原/森林：柔和。
4. **人工构筑特征**：`structure` 叠加规则几何（城墙方形=直角化；要塞星形=周期星角；港口半岛=一侧凸出）。
5. **扰动**：以 `seed` 播种的确定性 PRNG（mulberry32）为每个顶点沿法线加偏移，幅度 = `irregularity * r * noise`。
6. **平滑**：Catmull-Rom 采样（硬度由 `nature` 决定）；随后 **Douglas-Peucker 抽稀到 ≤64**。
7. **裁剪**：坐标夹到 0-100 域内。

**约束**：
- 同一 `(points, params, seed)` 必须产出完全一致的结果（可重放、可进版本历史对比）；
- 顶点数硬上限 64；
- 不产生自交多边形（生成后做一次简单自交检测，命中则降低 irregularity 重算一次）。

## 3. 交互（真人工作台）

| 操作 | 行为 |
|---|---|
| 生成形状 | 区域面板/详情「生成形状」→ 用成员据点 + 默认/AI 参数展开 → **预览**（半透明覆盖）→ 确认写入 draft（需显式保存入库） |
| 重新生成 | `auto` 模式直接重算；`manual` 模式先提示「会覆盖手绘顶点」再重算 |
| 编辑形状 | 进入顶点编辑：顶点可拖、双击边加点、右键顶点删点；退出编辑 → `mode = manual` 固化 |
| 层级 | 区域面板显示缩进树（可折叠）；区域详情可选父区域；画布按深度排序渲染（父在下、子在上） |
| 提示 | 据点落在所属区域形状外 → 警告条（引用不变） |

## 4. AI 链路与 Agent 工具

- **AI 只输出语义参数，不输出几何**（已确认）。
- 端点：`POST /api/v1/world-maps/{map_id}/regions/{region_id}/shape/generate`
  - 入参可显式给 `params`；未给时由 LLM 从「区域名 + 成员据点描述 + 项目题材」推断，
    以受控词表约束输出（JSON，值不在词表内则回退默认并记日志）。
  - 返回结果形状顶点供预览，**写入仍需走既有 revision CAS 保存**。
- Agent 工具：`generate_region_shape`（risk `write`），与真人共用同一 service 层；
  另有 `list_region_shape_presets`（只读，返回受控词表供 LLM 选值）。
- 文档同步：`docs/agent/agent-center.md` 补这两个工具。

## 5. 渲染

- 画布：区域渲染改用 `shape.vertices` → Leaflet `Polygon`（无顶点时按 1.3 回退）。
- 层级视觉（不限层，按深度自动计算）：

| 深度 | 填充 opacity | 边界 |
|---|---|---|
| 父（浅） | `.06` | 1.2px 虚线 |
| 子（深一级） | `.10` | 1.0px 实线 |
| 更深 | 每层 +`.02`，上限 `.18` | 同子层 |
| 选中 | 当前值 +`.08` | 主色实线 1.6px + 外发光 |

- 区域名标签沿用 LOD 规则（`docs/design/... §6.3`）：常驻、衬线、纸色描边。
- 导出：SVG `/render`、点位 JSON 导出同步输出 `shape`（JSON 增加 `shape` 字段）。

## 6. 据点类型扩展

`kind` 从 5 种扩到 **20 种**，每种配内联 SVG 图标（Lucide 风格，24×24、`stroke-width:1.75`、`currentColor`、禁 emoji）：

- 聚落（4）：村落 / 城镇 / 都城 / 庄园
- 军事（3）：城池 / 关隘 / 战场
- 交通（4）：港口 / 渡口 / 桥梁 / 驿站
- 人文（5）：集市 / 神殿 / 塔楼 / 废墟 / 陵墓
- 自然（4）：山峰 / 森林 / 湖泊 / 矿场
- 兜底（1）：其他

`KIND_OPTIONS.node` 与 `NODE_ICONS` 同步更新；未知 kind 回退「其他」图标。

## 7. 数据清理

- 一次性脚本：删除 `world_maps` 与 `world_map_revisions` 全部行。
- 执行前打印待删数量并向用户确认；脚本可重复执行（幂等）。

## 8. 验收标准

1. 同一 `(据点, params, seed)` 两次生成 → 顶点完全一致（单测覆盖）。
2. 顶点数 ≤64（单测覆盖三种 scale 与多个 seed）。
3. 成员据点移动后，auto 模式重新生成 → 形状随之变化；manual 模式不变。
4. 手绘编辑后 `mode = manual`，点「重新生成」有覆盖确认。
5. 三层嵌套（省/县/村）渲染：父淡子艳、选中提亮、层级顺序正确。
6. 据点在形状外：出现警告条且 `region_id` 未变。
7. 导出 JSON 含 `shape`；`/render` SVG 使用新几何。
8. Agent 工具 `generate_region_shape` 与真人链路产出一致（同一 service）。
9. 20 种据点 kind 均有图标，未知 kind 回退正常。
