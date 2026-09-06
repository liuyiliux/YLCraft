# 2026-09-06 世界地图：据点生成链路打通 + 事件日志收尾交接

## 一、本轮做了什么

### 1. 福贵项目「没有地图」的定位（结论：数据没丢，是从未生成）

接到"福贵没有地图、提取是不是只写了角色"的排查，先查库而不是先改代码：

| 表 | 行数 | 说明 |
|---|---|---|
| `world_entities` | 58 | 11 类实体齐全，其中 `entity_type=place` 有 5 个 |
| `world_fact_candidates` | 103 | 提取一直正常，最后一次成功在当天 19:27 |
| `world_map_documents` | **0** | 全库 6 个项目都没有地图文档 |
| `world_map_revisions` | **0** | 版本历史同样为空 |
| 平台事件日志 map 相关 | 0 条 | 事件日志有当天记录，说明不是被清理后连日志一起消失 |

结论：地图是**显式操作**（`from-places` 按钮 / agent 工具），不属于提取自动产物；该项目从未执行过生成。提取并没有"只写角色"，地点实体是齐的。

### 2. 工作台入口缺口：独立页无法选项目

`frontend/src/pages/world-map/index.tsx` 只从 URL 读 `project_id`。从侧边栏直接进入时没有参数 → `projectId` 为空 → 所有需要项目的按钮被禁用，页面却没有任何选择项目的入口。

修复：页面顶部新增**项目选择器**（可搜索），选中/切换写回 URL（`replace`，刷新和分享不丢），切换项目时清掉旧项目的 `snapshot_id` 避免错位恢复。深链进入时同样显示并高亮当前项目。

### 3. 地点实体的 region 属性接进地图（本轮核心）

`extraction.py` 的 `RELATION_HINTS` 早就定义了 `location: (("region", "part_of", "place"))`，提取也确实产出了区域信息——5 个地点实体的 `attributes_json.region` 分别是县城边 / 县城 / 村东头 / 村庄周边 / 镇上。但两处断链：

- `part_of` 关系要求 region 值能匹配到**同名 place 实体**，"县城""村东头"不是独立地点实体 → 静默跳过（库里关系只有 rival / enforced_by）
- `from-places` 建据点时写死 `"region_id": None`（注释写着区域由用户手动建）

改动（`backend/app/services/novel_source/world_map.py` 的 `create_map_from_project_places`）：

- 按 `region` 属性名**复用或新建地图区域**，据点 `region_id` 直接指向它
- **已在地图上但没归区的据点，重跑时按实体 region 补齐归属**——不重建据点，保留用户精修过的坐标
- 重复判定从"有新据点"放宽为"新据点 / 补了归属 / 建了区域任一"，否则重跑会直接报"无需重复生成"
- 区域对象带 `source: "place_region"` 标记来源，形状留空给后续生成/手绘

### 4. 顺手修掉的缺陷：初稿是 v2、且没有版本快照

`from-places` 新建地图时 revision 从 1 直接 +1 成 2，且完全不写 `world_map_revisions`——初稿无法回滚（这也是福贵 revisions 为 0 的原因）。改为：新建就是 v1，已有地图才递增；两种情况都落版本快照（`operator="from-places"`）。

### 5. zcode 遗留的事件日志增强收尾

zcode 额度耗尽留下了 4 个未提交文件的半成品，审查后补两处硬伤：

- `WorldGenerationService.draft_template` 自己发 LLM、不走 `_generate`，导致 draft 端点读的 `last_llm_meta` **恒为空** → 在该处独立记录 prompt/raw
- `WorldExtractionService._generate_json` 把调用明细 append 在"空内容重试"**之前**，会把重试前的空结果当最终值 → 挪到重试之后
- 两个服务类 `__init__` 补字段初始化

### 6. 验证：中文映射与地图几何确已完成

- 契约里 60+ 个属性键（`contracts.py` 各域 `attributes`）与 `frontend/src/utils/worldFieldLabels.ts` 逐条比对，**全部有中文标签**，且带单测
- 前端护栏：`worldFieldLabels.test.ts` 7 项 + `regionShape.test.ts` 16 项 = 23 项全过

### 7. part_of 关系物化：区域名不再被静默丢弃

`RELATION_HINTS` 里 `location: (("region", "part_of", "place"))` 要求 region 值能匹配到**同名 place 实体**，而"县城""村东头"这类区域名不会被原文当地点收录 → 匹配不到就静默跳过（福贵库里关系只有 rival / enforced_by）。

改动（`extraction.py`）：新增 `REGION_ENTITY_FIELDS = {("location", "region")}`，目标解析不到时调 `_upsert_region_entity` 补建 **`entity_type="region"`** 的实体承载区域名，再连 `part_of`。

关键取舍：区域用 `region` 而不是 `place`——`from-places` 只取 `place`，区域不会被当成据点生成到地图上。同名区域在索引里复用，不重复建。

### 8. 批量生成区域形状（前端）

形状仍由前端唯一展开（决策 D-1：后端只产参数与 seed）。新增「生成全部形状」按钮（顶部工具条），只给**还没有形状**的区域生成，已生成或手绘过的一律不动，避免覆盖用户精调的轮廓。写草稿后提示保存，不静默入库。

## 二、测试

后端 `tests/test_novel_source_world.py` **77 项全过**，其中本轮新增 3 项：

- `test_create_map_from_project_places_builds_regions`：3 个带 region 的地点建出 3 个区域，据点归属正确，重跑不重复
- `test_create_map_from_project_places_backfills_region`：先建图后补 region，重跑补上区域且**据点 id 不变**
- `test_create_map_from_project_places_writes_revision_snapshot`：初稿 v1、追加 v2，快照各落一条

## 三、必知坑

1. **地图是显式生成的**：提取写完地点实体不会自动有地图，必须点「从地点实体生成」。排查"没有地图"先查 `world_map_documents`，别急着怀疑提取。
2. **region 值粒度偏碎**：AI 提炼的"县城"和"县城边"是相邻片区，自动建区会出现 5 个区域各 1 个据点。区域名可在界面改，也能用 `parent_id` 挂父子层级。
3. **part_of 关系仍未物化**（本轮未做）：region 值匹配不到同名 place 实体时静默跳过，关系图谱里看不到"地点属于某区域"。要做的话得允许按文本建关系。
4. **本机后端环境缺依赖**：`asyncpg` / `psycopg2-binary` / `pgvector` / `aiofiles` 需手动装，否则连 import 都失败（`database.py` 模块级建引擎）。

## 四、收尾

本轮改动（含 zcode 遗留的事件日志补全）已一起提交：后端 5 个文件、前端 2 个文件、文档 3 个文件。

## 五、遗留候选

- 区域粒度偏碎时的合并引导（如把"县城"与"县城边"并成一个父区域）
- 地点实体的其它关系字段（如 faction 的 territory）是否也允许按文本补建目标实体
