# 任务 · 区域几何重构（region-geometry-rework）

> 规格：`./spec.md`　需求：`.ai-sdd/requirements/region-geometry-rework/discover-2026-09-04.md`
> 约定：每批完成后跑 `tsc` 双配置 + 页面冒烟；后端跑相关 pytest；文档同轮更新。

## 阶段 1 · 数据与算法地基 ✅

- [x] 1. 前端类型：区域新增 `shape`（mode / seed / params / vertices）；`parent_id` 原已存在并补注释。
      _Done: `api/novelSource.ts` 新增 `WorldMapRegionShape` 并挂到 `WorldMapRegion.shape`（可选，缺失视为未生成）。_
- [x] 2. 新增 `frontend/src/utils/regionShape.ts`：确定性 PRNG（mulberry32）、基础骨架（6 种聚落形态）、
      自然意象修正（8 种）、人工构筑特征（3+）、扰动、Catmull-Rom 平滑、Douglas-Peucker 抽稀到 ≤64、坐标裁剪。
      _Done: 输出顶点为 `[y, x]`（与 Leaflet 一致）；骨架先按最远据点留 15% 余量包住成员据点，再按面积感外扩，
      因此 scale 始终有效（小<中<大）且形状一定包得住据点；自交时降不规则度重算一次，仍自交则退回平滑前骨架。_
- [x] 3. 受控词表常量：`NATURE_IMAGERY` / `SETTLEMENT_FORMS` / `STRUCTURE_FORMS`，供 UI、AI 与后端共用。
- [x] 4. 算法校验（8 项全通过）：同参数同 seed 一致、不同 seed 不同、顶点 ≤64（全形态×意象×构筑×不规则度
      组合）、坐标裁剪 0-100、无据点可用、面积感递增、60 seed × 最破碎参数顶点合法、hashSeed 稳定。
      _校验脚本 `tmp/check-region-shape.mjs`（tsc 编译到 tmp 后用 node 跑）。注：前端目前无单元测试框架，
      建议后续引入 vitest 把这类纯函数测试固化（见待办 D-2）。_

## 阶段 2 · 画布渲染 ✅

- [x] 5. `MapCanvas`：区域改用 `shape.vertices` 渲染；无顶点时按 `seed = shape.seed ?? hash(region.id)`
      在内存中临时生成（不写库），因此未生成形状的区域也不会变空白。
      _Done: 新增 `resolveRegionVertices()`；渲染条件放宽为「有成员据点 **或** 已存形状」，
      不再要求 ≥3 个据点（旧凸包实现的最小三点限制被移除）。_
- [x] 6. 层级视觉：`computeRegionDepths()` 按 `parent_id` 链算深度（带环检测，上限 8 层），
      `regionPathStyle()` 给出填充/边界/虚线：父 .06 + 粗虚线、子 .10 + 细实线、更深每层 +.02（上限 .18）、
      选中填充 +.08 且边界转主色 1.6px。渲染按深度排序（父先画、子压在上面）。
      _Done: 选中据点时，其所属区域一并提亮（`selectedRegionId`）。_
- [x] 7. 区域名标签保持常驻（LOD 不变）。_嵌套重叠策略待阶段 3 与层级树一起调（当前父标签淡化已通过
      填充权重间接实现）。_
- [x] 补充：AI/后端传入的 `shape.params` 经 `normalizeShapeParams()` 收敛回受控词表
      （越界回退默认），脏数据不会把形状算崩；删除不再使用的 `REGION_FILL_OPACITY` 常量。

## 阶段 3 · 交互 ✅

- [x] 8. 左栏数据面板新增「区域形状」列表：每个区域一行（名称 / 顶点数与是否手绘 / 生成或重新生成 / 编辑），
      未生成形状的区域给橙色提示「画布显示的是临时形状（未入库）」。
      _Done: 生成后直接写入 draft（**不自动入库**，仍需显式保存），因此可撤销——比"预览态"更简单且符合既有纪律。_
- [x] 9. 「重新生成」：`auto` 换 seed 直接重算；`manual` 用 Modal.confirm 提示会覆盖手绘顶点
      （并提示可用版本历史找回）。
- [x] 10. 顶点编辑：进入编辑后画布出现方块手柄，改动即写回顶点并**固化为 `manual`**，
      避免之后被自动重算悄悄覆盖。拖动手柄微调；**双击边在最近边处加点**（编辑态自动关闭地图双击缩放，
      顶点达 64 上限拒绝并提示）；**右键顶点删点**（少于 3 个顶点拒绝）。
      _Done: `nearestEdgeIndex` 纯函数定位插入点（有测试）；编辑中区域轮廓加十字光标。_
- [x] 11. 区域层级树：面板按 parent_id 树序缩进显示（可折叠），每行内联选择父区域，
      成环/自指/超深（>8 层）经 `canReparent` 统一校验（不合法选项置灰、批量编辑入口写前拦截）。
      _Done: 新增 `utils/regionHierarchy.ts`（`computeRegionDepths` / `canReparent` / `regionDisplayOrder`），
      MapCanvas 深度计算改为共用该实现；断链/成环等脏数据显示层平铺兜底不丢行。_
- [x] 12. 据点落在所属区域外：画布上方 `--p-warn` 警告条（列据点名，引用不变）+
      据点详情面板警告框。区域未生成形状时不判定（临时兜底形状不是正典）。
      _Done: `pointInPolygon` 射线法纯函数（凹多边形正确、边界视为在内），有测试。_

## 阶段 4 · 后端与 Agent ✅

- [x] 13. 后端区域结构校验与序列化支持 `shape` / `parent_id`（宽松校验，未知字段保留）。
      _Done: `world_map.py` 新增 `sanitize_map_json`，create/update/from-places 写入库路径统一过一道：
      区域顶点收敛 `[y,x]` 数字对、0-100 裁剪、截断 ≤64（`MAX_SHAPE_VERTICES`）、非法项丢弃；
      `parent_id` 只收 None/字符串；`shape` 非对象则丢弃（前端按"未生成"兜底）；
      区域未知字段与节点/路线/空间层原样透传。_
- [x] 14. 端点 `POST /api/v1/world-maps/{map_id}/regions/{region_id}/shape/generate`：
      显式参数直接校验返回（越界回退默认 + 记录 `fallbacks`）；未给时由 LLM 从
      「区域名 + 成员据点描述 + 项目题材（title/project_type，尽力而为）」推断，
      以受控词表约束输出（JSON 围栏/闲话容忍，解析失败报错）。
      _Done: 按 D-1 **只返回语义参数 + seed、不含顶点**（顶点由前端展开预览），预览不落库；
      seed 缺省按区域 id 做 FNV-1a 稳定派生（与前端 `hashSeed` 同算法）。
      实现：`services/novel_source/world_map_shape.py` + `api/v1/novel_sources.py`。_
- [x] 15. ~~展开算法服务端实现（Python 版）~~ **取消**（决策 D-1 已定稿：几何由前端唯一实现）。
      服务端 `/render` 与导出只消费**已入库**顶点，不做参数展开。
- [x] 16. Agent 工具：`generate_region_shape`（write）、`list_region_shape_presets`（read），
      与真人共用 service；测试覆盖参数校验与词表越界回退。
      _Done: 工具写 `mode/seed/params`（顶点留空，前端展开显示）并走 CAS 落历史快照；
      手绘（manual）区域默认拒绝覆盖，`overwrite=true` 放行；LLM 推断消耗一次文本配额。
      测试：`tests/test_world_map_shape.py`（词表回退 / 落库 / 手绘保护 / LLM 推断 / 预设词表）。_
- [x] 17. 导出与 `/render`：SVG 使用新几何；点位 JSON 增加 `shape` 字段。
      _Done: `render_map_svg` 画已入库区域多边形（父淡子艳：父 .06 虚线、更深 .10+.02/层，
      深度按 parent_id 链算、断链/成环安全封顶 8；无顶点区域跳过）、区域名标签在顶点均值处；
      导出 `build_map_export` 的 `regions` 本就原样透传，`shape` 随之带出。_

## 阶段 5 · 据点类型与图标 ✅

- [x] 18. `KIND_OPTIONS.node` 扩到 20 种（聚落/军事/交通/人文/自然/兜底）。
      _Done: 新增纯模块 `utils/nodeKinds.ts` 作单一数据源：20 内容 kind
      （聚落 4：村落/城镇/都城/庄园；军事 3：城池/关隘/战场；交通 4：港口/渡口/桥梁/驿站；
      人文 5：集市/神殿/塔楼/废墟/陵墓；自然 4：山峰/森林/湖泊/矿场）+ 兜底「其他」= 21 选项
      （规格 §6 分组清单之和；「20 种」计内容 kind）。`WorldMapEditor` 的选项/新建默认值
      （默认 `村落`）与图层筛选全部接入。_
- [x] 19. `NODE_ICONS` 补齐 20 个内联 SVG（Lucide 风格），未知 kind 回退「其他」。
      _Done: 21 个图标（24×24、`stroke-width:1.75`、`currentColor`、淡填充、禁 emoji）+ 旧数据
      别名（据点→村落、场景、其它→其他）；`nodeIconSvg()` 统一兜底。
      测试 `utils/nodeKinds.test.ts` 5 项：数量/唯一性、全覆盖、回退、风格约束、默认值。_

## 阶段 6 · 数据清理与收尾 ✅

- [x] 20. 一次性清库脚本（幂等）：删除 `world_maps` + `world_map_revisions`，执行前打印数量并确认。
      _Done: `backend/scripts/cleanup_world_maps.py`（加载 backend/.env 与应用同库；
      打印两表行数 → 交互输入 yes 或 `--yes` 才执行；空表无事发生）。
      已执行：`world_maps` 1 行、`world_map_revisions` 3 行删除；复跑验证幂等（空表无事发生）。
      本地遗留空文件 `backend/ylcraft.db`（无表）未动，与配置库无关。_
- [x] 21. 文档：架构文档（区域几何语义 + 层级）、样式规范（层级视觉表、20 图标）、
      `docs/agent/agent-center.md`（新工具）。
      _Done: 架构文档「区域几何」小节覆盖阶段 1-4 全部语义（阶段 4 补齐）；样式规范 §6.3
      改为层级视觉表 + 21 kind 说明、§7 补地物图标语义映射；agent-center.md 已在阶段 4 补
      两个工具（14 工具）；`docs/README.md` 清除残留的「势力范围多边形」旧语义并更新最近状态。_
- [x] 22. 逐条对照 `spec.md` §8 验收标准自检。
      _Done（2026-09-05，证据如下）_：
      1. 同 (据点, params, seed) 两次生成一致 — vitest「同一组参数与 seed 必须产出完全一致的形状」。
      2. 顶点 ≤64 — vitest「任何形态组合下顶点数都不超过上限」（全词表组合）+ 后端 `sanitize_map_json` 截断。
      3. 据点移动后 auto 重算形状随之变化 / manual 不变 — 生成以成员据点坐标为输入（面积感、
         据点必被包住测试）；manual 渲染始终用已存顶点，重算需确认。
      4. 手绘后 `mode=manual`，重新生成有覆盖确认 — 拖/加/删顶点均固化 manual；`Modal.confirm` 提示。
      5. 三层嵌套渲染 — `regionHierarchy` 深度/树序测试 + SVG 渲染测试（父 .06 虚线先画、子 .10 实线后画）。
      6. 据点越界警告且 `region_id` 未变 — `pointInPolygon` 测试 + 画布警告条/详情框（引用不改）。
      7. 导出 JSON 含 `shape`、`/render` 用新几何 — `build_map_export` 携带 shape 测试 + SVG polygon 测试。
      8. Agent 与真人同一链路 — 同用 `generate_region_shape_params`（同一词表校验与推断 service）。
      9. 21 选项均有图标、未知回退 — `nodeKinds` 测试（全覆盖 + 回退 + 风格约束）。

## 决策记录

- **D-1 算法实现位置（已定稿）**：**几何由前端 TS 唯一实现**，后端与 Agent 不实现几何。
  AI/Agent 只产出**语义参数**（受控词表 + seed + 面积感 + 不规则度），顶点一律由
  `frontend/src/utils/regionShape.ts` 展开。理由：单一实现、零双份维护、天然一致，
  且实时预览与参数微调都在前端完成。任务 15（Python 复刻）取消。
- **D-2 前端单元测试框架（已完成）**：引入 **vitest 1.6.0**（与项目 vite 5 匹配；最新版会因 peer
  冲突装不上，不追新）。`npm test` / `npm run test:watch`。当前两个测试文件共 **27 项**：
  `src/utils/regionShape.test.ts`（形状 9 项 + 越界判定/最近边定位 7 项）、
  `src/utils/regionHierarchy.test.ts`（深度/成环校验/树序 11 项）。
  后续纯函数（导出、坐标换算等）都应补测试。
