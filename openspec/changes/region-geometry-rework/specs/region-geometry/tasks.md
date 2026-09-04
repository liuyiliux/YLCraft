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

## 阶段 2 · 画布渲染

- [ ] 5. `MapCanvas`：区域改用 `shape.vertices` 渲染；无顶点时按 `seed=hash(region.id)` 内存回退生成。
- [ ] 6. 层级视觉：按 `parent_id` 计算深度 → 填充 opacity（父 .06 / 子 .10 / 每层 +.02 上限 .18）、
      边界（父虚线粗、子实线细）、选中提亮 + 主色描边。
- [ ] 7. 区域名标签保持常驻（LOD 规则不变），嵌套时不重叠策略：子标签偏移，父标签淡化。

## 阶段 3 · 交互

- [ ] 8. 区域面板/详情新增「生成形状」：预览 → 确认写入 draft（不自动入库）。
- [ ] 9. 「重新生成」：`auto` 直接重算；`manual` 弹确认提示覆盖手绘顶点。
- [ ] 10. 顶点编辑模式：顶点可拖、双击边加点、右键顶点删点；退出即 `mode=manual` 固化。
- [ ] 11. 区域层级树：面板缩进显示（可折叠），区域详情可选父区域，禁止形成环。
- [ ] 12. 据点落在所属区域外：`--p-warn` 警告条（引用不变，不自动归属）。

## 阶段 4 · 后端与 Agent

- [ ] 13. 后端区域结构校验与序列化支持 `shape` / `parent_id`（宽松校验，未知字段保留）。
- [ ] 14. 端点 `POST /api/v1/world-maps/{map_id}/regions/{region_id}/shape/generate`：
      显式参数直接展开；未给时由 LLM 推断并以受控词表约束输出（越界回退 + 记日志）。
- [ ] 15. 展开算法服务端实现（与前端同一套规则，Python 版）或前端唯一实现 + 后端仅存结果（待定，见决策 D-1）。
- [ ] 16. Agent 工具：`generate_region_shape`（write）、`list_region_shape_presets`（read），
      与真人共用 service；测试覆盖参数校验与词表越界回退。
- [ ] 17. 导出与 `/render`：SVG 使用新几何；点位 JSON 增加 `shape` 字段。

## 阶段 5 · 据点类型与图标

- [ ] 18. `KIND_OPTIONS.node` 扩到 20 种（聚落/军事/交通/人文/自然/兜底）。
- [ ] 19. `NODE_ICONS` 补齐 20 个内联 SVG（Lucide 风格），未知 kind 回退「其他」。

## 阶段 6 · 数据清理与收尾

- [ ] 20. 一次性清库脚本（幂等）：删除 `world_maps` + `world_map_revisions`，执行前打印数量并确认。
- [ ] 21. 文档：架构文档（区域几何语义 + 层级）、样式规范（层级视觉表、20 图标）、
      `docs/agent/agent-center.md`（新工具）。
- [ ] 22. 逐条对照 `spec.md` §8 验收标准自检。

## 决策记录

- **D-1 算法实现位置（已定稿）**：**几何由前端 TS 唯一实现**，后端与 Agent 不实现几何。
  AI/Agent 只产出**语义参数**（受控词表 + seed + 面积感 + 不规则度），顶点一律由
  `frontend/src/utils/regionShape.ts` 展开。理由：单一实现、零双份维护、天然一致，
  且实时预览与参数微调都在前端完成。任务 15（Python 复刻）取消。
- **D-2 前端单元测试框架（待办）**：前端目前无任何单测框架（只有 `smoke:pages` 脚本），
  本次算法校验用「tsc 编译到 tmp + node 断言」临时方案。建议引入 vitest 固化纯函数测试。
