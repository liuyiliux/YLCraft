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

**参考组合页（2026-11-01 新增）**：`photo-ref/combo.html`
—— 脸 / 服装 / 姿势各抽一件，自动拼出提示词。分类法照 `sleepy-zone/ai-ref-library-cn`
（脸库 / 姿势库 / 服装库 + 随机组合），**条目是本项目自己的示例数据，不含任何第三方图片**，
所以图位是明确的占位而不是假照片。入口在参考库顶栏「参考组合」。
许可提醒写在页面底部：那三个库只有脸库是 CC0，姿势/服装库禁止再分发图片本体。

#### ⚠️ 指定角色 vs 随机人设：两个入口，不是「先随机再锁」（2026-11-01 用户澄清）

用户原话：「生成一个指定的角色 和 生成一个随机角色 是不同的，这个指定的角色包括动漫游戏
肯定是衣服样貌固定的，或者是我上传一个参考照片 脸是不变的。」

所以是**两种模式**，不是一个模式加个锁：

| | 指定角色 | 随机人设 |
|---|---|---|
| 用途 | 拍**这个特定的人** | 找灵感、试方向 |
| 脸 | **锁定**（来自设定 / 档案 / 参考照）| 可抽 |
| 服装 | **看来源**（见下表）| 可抽 |
| 姿势 | 可换 —— 这是拍摄变量 | 可抽 |
| 光线 / 场景 | 跟项目走，**从不随机** | 同 |

**指定角色内部，三种来源的自由度还不一样**：

| 来源 | 脸 | 服装 | 提示词要写的约束 |
|---|---|---|---|
| **官方角色（IP / 动漫 / 游戏）** | 锁 | **锁死** | 「不要改动发色、瞳色、服饰配色与纹样」——换了就不是这个角色 |
| **模特档案（真人）** | 锁 | 可换，但换的是**她的**衣橱 | 「脸型五官不要变」 |
| **上传参考照片** | 锁 | 可换（沿用原图 / 另换一套）| 「同一人物（按参考照片）…脸型五官不要变」 |

UI 上用**两种锁色**区分：青色 = 来自角色/档案，黄色 = 官方设定不可改。

随机人设抽到满意的脸 →「定成角色」，转成指定角色，之后不再随机。

**一句话**：随机是"还没决定拍谁"，指定是"已经决定了拍谁"。决定之后，脸和造型都不该再被抽到。

**场景与光线从项目读（2026-11-01 补）**：页面上多了一条「给哪个项目拍」，
选秋天颐和园 / 民政局门口 / 棚拍，下面的「场景与光线」块跟着变，并明确标 **来自项目 · 不随机**。
提示词里的地点、光线、色调全部来自这里 —— 之前这三项是写死的常量 LIGHT，
嘴上说"跟项目走"、代码里没做，等于假规则。

真实现时把 `PROJECTS` 换成项目记录查询（字段：`place` / `light` / `tone`），
提示词模板不用改。

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
