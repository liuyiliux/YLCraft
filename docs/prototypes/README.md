# docs/prototypes 索引

> **这是索引，不是介绍文档。** 70+ 份原型文档，没有索引就没人找得到。
> 新加原型文档必须登记到这。
>
> ⚠️ **原型不是实现事实**。要落地前先看真代码，别把原型当规格。

---

## 一、当前在做的（2026-11-01）

| 文档 | 原型文件 | 状态 |
|---|---|---|
| [`AGENT_PAGE_SA.md`](./AGENT_PAGE_SA.md) | `photo-ref/agent-page.html` | **当前版**（v9）：三栏 + 状态条一条（圆点单行、与内容列对齐）+ 点图弹多角度 + 左栏单行 + 空态 2×2 卡片 + 跑起来能停 + 指标条 |
| [`AGENT_PAGE_HISTORY.md`](./AGENT_PAGE_HISTORY.md) | — | reference：六条原则改动 + v5→v6 视觉修正的详解与实测记录 |
| [`AGENT_PAGE_FEATURE_AUDIT.md`](./AGENT_PAGE_FEATURE_AUDIT.md) | `photo-ref/agent-page.html` | **核对表**（2026-11-01）：v5 原型 vs 真代码，逐条标了丢没丢 + `file:line` 证据。视觉层未核对 |
| [`PREVIS_AGENT_V1.md`](./PREVIS_AGENT_V1.md) | `previs/director-agent.html` | **当前版**（v3）：3D 导演台 + 助手浮层 |
| [`MULTI_ANGLE_V1.md`](./MULTI_ANGLE_V1.md) | `canvas/multi-angle.html` | 已并入 Agent 页的弹窗，独立页留作参考 |
| [`HARNESS_DECISION_V1.md`](./HARNESS_DECISION_V1.md) | `harness_decision.html` | harness 四个方案对比（已讨论完，结论见 research） |

### 对应的调研
- `docs/research/SUPER_AGENT_RESEARCH.md` —— 上述 Agent 页/预演助手的指导思想来源

### ⚠️ 已废弃但没删
`AGENT_PAGE_V1.md` / `V2.md` / `V3.md` —— 是 v1~v3 的历史记录，
**其中 v1/v2 的部分设计已被推翻**（如「右边固定放素材库」）。
看现状请读 `AGENT_PAGE_SA.md`。

---

## 二、画布系列（48 份，最大的历史包袱）

按迭代顺序，**看最新一份就够**：

`CANVAS_GRAPH_V6` → `CANVAS_FLOWS_V8` → `CANVAS_PROTOTYPE_V9` →
`CANVAS_FREE_V10` → `CANVAS_FREE_V11` → `CANVAS_INSPECT_V12` →
`CANVAS_SHOTWALL_V13` → **`CANVAS_UNIFIED_V14`（最后一份主文档）**

V14 之后的补丁：
- `CANVAS_GRAPH_EDITABLE_V14_3.md`
- `CANVAS_IMAGE_OPS_V14_4.md` / `_V14_5.md`
- `CANVAS_P0_THREE_DONE.md` / `P1_DONE` / `P2_P3_P4` / `P5_SKILL_CAPS`

按主题：
| 主题 | 文档 |
|---|---|
| 元素增删 / 可编辑 | `CANVAS_ELEMENT_ADD_REMOVE.md`、`CANVAS_ELEMENT_EDITABLE.md` |
| 图层与撤销 | `CANVAS_LAYERS_AND_UNDO_REAL.md` |
| 蒙版与混合 | `CANVAS_MASK_AND_BLEND_DONE.md` |
| 搜索流程与失败 | `CANVAS_SEARCH_FLOW.md`、`CANVAS_SEARCH_FAILURES.md` |
| 检视面板 | `CANVAS_INSPECT_GRADED.md` + `CANVAS_INSPECT_V12.md` |
| 浮动工具条 | `CANVAS_FLOATBAR.md` |
| 非破坏导出 | `CANVAS_NONDESTRUCTIVE_EXPORT.md` |
| 模板 / 版本 | `CANVAS_TEMPLATE_VERSION.md` |
| 多租户与额度 | `CANVAS_TENANT_AND_CREDITS.md` |
| 本地编辑链路 | `CANVAS_LOCAL_EDIT_RAW_CHAIN.md` |
| 风格总汇 | `CANVAS_STYLE_AGGREGATED.md`（18KB）、`CANVAS_CONCEPT_AND_STYLE.md` |

**⚠️ 这 48 份没有清理过，互相重复很多。** 真要看画布现状，
以 `docs/prototypes/canvas/` 的代码为准，文档只当历史。

---

## 三、摄影 / 修图

| 文档 | 说明 |
|---|---|
| ⚠️ `PHOTO_REFERENCE_LIBRARY_REQUIREMENTS.md`（**224KB**） | **待拆，别当范例**。`AGENTS.md` 已标注 |
| `PHOTO_GAP_AUDIT.md` | 15 项功能差距审计（已全部关闭） |
| `GAP_CHECK_VS_PIXCAKE_PS.md` | 对照 Pixcake / PS 的差距 |
| `EDITOR_GAP_ANALYSIS.md` | 编辑器差距分析 |

---

## 四、平台外壳 / 其他

| 文档 | 说明 |
|---|---|
| `PLATFORM_SHELL_V16.md` / `V17.md` | 平台外壳（导航/布局） |
| `PROTOTYPE_GAP_ANALYSIS.md` | 原型整体差距 |
| `PROTOTYPE_REMAINING_SCOPE.md` | 剩余范围 |
| `WORKBUDDY_BRIEF.md` | 给 workbuddy 1024 活动的产品简报（4,190 字符） |
| `ASR_MODEL_TEST.md` | 语音识别模型选型（结论：星辰 Ultra，免费） |
| `CUE_DESIGN_DRAFT.md` | 提示/线索设计 |
| `KB_*.md` | 知识库设计 |
| `ELEMENT_*.md` / `LAYERED_*.md` | 分层素材设计 |
| `DISCUSS_NAMING_AND_REPAIR.md` | 命名与修复讨论 |
| `STYLE_V2_NOTES.md` | 风格 v2 |

---

## 五、原型页面怎么打开

**端口 8901**（⚠️ 8899 被另一个项目 `G:\摄影\YL摄影\site` 占用，别抢）：

```powershell
# 在 docs/prototypes 目录起服务
python -m http.server 8901 --bind 127.0.0.1 --directory F:\PycharmProjects\YLCraft\docs\prototypes
```

| 原型 | URL |
|---|---|
| Agent 页面 | `http://127.0.0.1:8901/photo-ref/agent-page.html` |
| 3D 导演台 + 助手 | `http://127.0.0.1:8901/previs/director-agent.html` |
| 多角度（独立页） | `http://127.0.0.1:8901/canvas/multi-angle.html` |
| harness 方案对比 | `http://127.0.0.1:8901/harness_decision.html` |
| 摄影参考库 | `http://127.0.0.1:8901/photo-ref/index.html` |
| 画布 | `http://127.0.0.1:8901/canvas/index.html` |

**改完必须加 `?nc=<随机>` 防缓存假阴性**（`AGENTS.md` 的规定）。

---

## 六、登记规则

- 新加原型文档 → 在本文档对应分区加一行
- 原型被推翻 → 不要删，移动到「已废弃」并写清被谁取代
- **单篇 ≤12KB**，超了拆主文件 + reference 子文件
