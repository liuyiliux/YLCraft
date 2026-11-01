# docs/prototypes 索引

> **这是索引，不是介绍文档。** 70+ 份原型文档，没有索引就没人找得到。
> 新加原型文档必须登记到这。
>
> ⚠️ **原型不是实现事实**。要落地前先看真代码，别把原型当规格。

---

## 一、当前在做的（2026-11-01）

| 文档 | 原型文件 | 状态 |
|---|---|---|
| [`AGENT_PAGE_SA.md`](./AGENT_PAGE_SA.md) | `photo-ref/agent-page.html` | **当前版**（v11）：三栏 + 状态条一条（圆点单行、与内容列对齐）+ 点图弹多角度 + 左栏单行 + 空态 2×2 卡片 + 跑起来能停 + 指标条 + 过程折叠带预算 + `/` 技能 |
| [`AGENT_PAGE_HISTORY.md`](./AGENT_PAGE_HISTORY.md) | — | reference：**v5 之后每一轮的改动详解与实测**（第 7~11 节，按需查）|
| [`AGENT_PAGE_HISTORY_V1_V4.md`](./AGENT_PAGE_HISTORY_V1_V4.md) | — | reference：v1~v4 六条原则改动（2026-11-01 从 HISTORY 拆出）|
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

**参考组合页（2026-11-01）**：`photo-ref/combo.html`
—— 脸 / 服装 / 姿势三维参考，入口在参考库顶栏「参考组合」。分类法照
`sleepy-zone/ai-ref-library-cn`（脸库 / 姿势库 / 服装库），**条目是本项目自己的示例数据，
不含任何第三方图片**，图位是明确的占位。许可提醒写在页面底部：那三个库只有脸库是 CC0，
姿势/服装库禁止再分发图片本体。

#### 主流程是「按场景推荐」，不是随机抽（2026-11-01 用户指出）

用户原话：「摄影这个应该是根据场景 ai 推荐参考图吧」。

**这条把主交互整个翻了**：摄影师的工作流是「我要拍秋天颐和园的小林」，
不是「给我抽个盲盒」。随机抽只在"没想法"时用。

| 模式 | 什么时候用 | 脸 | 服装 / 姿势 |
|---|---|---|---|
| **按场景推荐**（默认） | 有明确项目 | 项目里的人，**不参与推荐** | AI 按项目光线/地点/色调给 3 组 + **每组说清为什么** |
| 自己拼 | 想微调推荐结果 | 锁（按角色） | 可换 |
| 随机探索 | 没想法、找方向 | 可抽 | 可抽 |

推荐的价值不在组合叠加，**在于理由**。例：「项目是斜侧逆光，3⁄4 侧才吃得到边缘光；
十月风大，大衣压得住；靠墙站不抢长廊的纵深。」

#### 同一批库，两种读法

| 给谁用 | 脸 | 姿势 | 服装 |
|---|---|---|---|
| **摄影师**（人看） | 定妆、角度 | 构图、机位 | 搭配、配色 |
| **生图模型**（模型读） | IP-Adapter / 人脸一致 | ControlNet OpenPose | 参考图 / 换装 |

这两个用途共用一份数据，别再各建一套库。

#### 随机与固定的边界

| 维度 | 规则 |
|---|---|
| **脸** | 指定角色时**永远锁**（IP 设定 / 模特档案 / 上传参考照），不进随机池 |
| **服装** | IP 角色**锁死**（换了就不是这个角色）；真人可换，但换的是**她的衣橱** |
| **光线 / 场景** | **从来不随机**，跟项目走（`PROJECTS` 提供 place / light / tone）|

UI 用两种锁色：青色 = 来自角色/档案，黄色 = 官方设定不可改；项目条固定用黄色，
和角色来源的青色分开 —— 两类信息的来源不同。

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
| 参考组合（脸/服装/姿势） | `http://127.0.0.1:8901/photo-ref/combo.html` |
| 画布 | `http://127.0.0.1:8901/canvas/index.html` |

**改完必须加 `?nc=<随机>` 防缓存假阴性**（`AGENTS.md` 的规定）。

---

## 六、登记规则

- 新加原型文档 → 在本文档对应分区加一行
- 原型被推翻 → 不要删，移动到「已废弃」并写清被谁取代
- **单篇 ≤12KB**，超了拆主文件 + reference 子文件
