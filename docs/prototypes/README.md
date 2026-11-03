# docs/prototypes 索引

> **先看「零、原型总览」**——现在有哪几个原型、各自解决什么、最近在改什么。
> 下面是细节索引：73 份文档按主题分类，新加必须登记到这。
>
> ⚠️ **原型不是实现事实**。要落地前先看真代码，别把原型当规格。

---

## 零、原型总览（2026-11-03）

> 最近在做的是**重新设计页面原型**，所以先说清「一共有几个、各自在解决什么」。
> 下面这张表是唯一入口，其它章节都是细节。

### 现在活的原型：3 个

| # | 原型 | 入口 | 解决什么问题 | 状态 | 体量 |
|---|---|---|---|---|---|
| **1** | **画布** | `canvas/index.html` | AI 创作工作台：镜头墙 / 素材墙（原「自由画布」，11-03 改名）/ 高级流程三视图 | 🔧 **正在重做视觉** | 18KB + 33 js + 6 css |
| **2** | **摄影参考库** | `photo-ref/index.html` | 摄影师的参考库（一张片子 + 偷师点）＋ 拍摄计划 | ✅ 稳定 | 424KB + 5 子页 |
| **3** | **Agent 页** | `photo-ref/agent-page.html` | 跟 AI 对话协作的三栏界面（左会话 / 中工作区 / 右产物）| ✅ 11-01 定版 | 104KB |
| — | 平台壳 | `platform_shell_v17.html` | 首页 / 工作区外壳（早期形态，未继续） | ⏸ 停 | 85KB |

### 三者的关系（别搞混）

```
摄影参考库      拍之前的功课：参考别人的片子（偷师点）、做拍摄计划
     ↓ 决定了怎么拍
画布            干活的地方：拆分镜、出图、改图
     ↑ 同一个协作形态的完整版
Agent 页        跟 AI 说话 + 看过程 + 收产物（画布右面板就是它的精简版）
```

**判断一个改动该放哪**：看这个页面的**单位**是什么。
- 一张**片子**（缩略图 + 参数 + 偷师点）→ 摄影参考库
- 一张**素材 / 一个镜头**（卡片 + 角标）→ 画布
- 一段**对话 + 一份产物** → Agent 页

> 踩过的坑：2026-11-02 把「脸/服装/姿势三格拼装」（生图素材）硬塞进摄影参考库，
> 还在它顶栏加了入口 —— 那套东西的单位是「一张条件图」，属于画布的生图链路，
> 不是「一张片子」。后来挪成画布对话里的弹层（`66f80b94`）。

### 最近在重新设计什么（2026-11）

| 改动 | 结果 |
|---|---|
| 画布顶栏收工具 | 20 个元素 → 9 个，其余进「⋯」菜单（`77c9a70c`）|
| 镜头卡补属性 | 左下**景别**、右下**角色**，统计栏出景别分布（`8d8fdeb3` `58fcfb22`）|
| 题材区分 | 人物片（有角色/空镜）· 角色图（按角度）· 宣传片（**无角色**）（`bf2e42ff`）|
| 生图参考组合 | 不做独立页，改成画布对话里说「凑一组参考」弹出的面板（`66f80b94`）|

### 历史版本：别改、别当规格

`v2`–`v15` 十八个版本目录 + 27 个 `canvas_*.html`（`canvas_prototype` /
`canvas_layers_v4/v5` / `canvas_free_v10/v11` / `canvas_shotwall_v13` …）。
`canvas_unified_v14.html` 现在只是 1KB 的跳转页，真内容在 `canvas/` 目录。

**看现状只认 `canvas/` / `photo-ref/` 两个目录里的代码。**

---

## 一、Agent 页细节索引（11-01 定版）

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

### 生图参考组合：画布里的弹层，不是独立页面（2026-11-01）

**曾经做过一版独立页 `gen-ref/`，已删。** 原因：独立页得自己造一个「场景选择器」，
但生图的场景本来就该从**对话**里来（「给小林在颐和园拍一张逆光的」），
自己再造一个下拉就是重复且空转。

现在的形态：**在画布里说一句含「参考」的话**（凑一组参考 / 要一组参考 / 找参考）→
弹出「凑一组参考」面板：

| 面板里 | 内容 |
|---|---|
| 读到的场景 | 从这句话里解析出 地点 / 光线 / 色调，并标出命中了哪个词 |
| 说明 | 明确写出「来源：你刚说的那句「…」」+ 「脸按角色档案，不参与推荐」 |
| 3 条推荐 | 服装 + 姿势 + **为什么这么搭**；点一条写进输入框，用户还能改 |

分类法照 `sleepy-zone/ai-ref-library-cn`（脸 / 姿势 / 服装），
条目是本项目自己的示例数据，不含第三方图片。

| 维度 | 规则 |
|---|---|
| **脸** | 按角色档案，**不参与推荐**（不进随机池） |
| **服装** | IP 角色锁死；真人可换，但换的是**她的衣橱** |
| **光线 / 场景** | **不随机**，从对话里读 |

> 这仍然是生图，不是摄影。摄影那边要的是「怎么拍」（景别 / 机位 / 偷师点），
> 见第三节 `photo-ref/index.html`。两套界面别混。

---

## 三、摄影 / 修图

| 文档 | 说明 |
|---|---|
| ⚠️ `PHOTO_REFERENCE_LIBRARY_REQUIREMENTS.md`（**224KB**） | **待拆，别当范例**。`AGENTS.md` 已标注 |
| `PHOTO_GAP_AUDIT.md` | 15 项功能差距审计（已全部关闭） |
| `GAP_CHECK_VS_PIXCAKE_PS.md` | 对照 Pixcake / PS 的差距 |
| `EDITOR_GAP_ANALYSIS.md` | 编辑器差距分析 |

**摄影参考库的结构（别动，这是它的长处）**：`photo-ref/index.html`
—— 以**一张片子**为单位：缩略图 + 来源徽标（电影 2.39 / 小红书 / B站截帧 03:24）+ RAW 标
＋**偷师点**（自己写的一句话，如「逆光把发丝和背景分开，脸留暗部」）＋标签；
点开是「大图 + 完整参数 + 偷师点 + 编辑」。三个库：审美 / 反思 / 作品。

> ⚠️ **2026-11-01 我犯过一次错**：把 AI 生图素材库的「脸 / 服装 / 姿势三格拼装」
> 硬塞进摄影参考库，还覆盖了入口。摄影要的是「**怎么拍**」（景别、机位、光线、偷师点），
> 生图要的是「**拿什么条件喂模型**」（三张条件图 + 提示词）—— 两件事，两套界面。
> 生图那套已移到 `gen-ref/`，见第二节末尾。

**修图相关**：`GAP_CHECK_VS_PIXCAKE_PS.md`（对照 Pixcake / PS）、`EDITOR_GAP_ANALYSIS.md`（编辑器差距）。
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
| **原型启动页（根路径，画布在首位）** | `http://127.0.0.1:8901/` |
| 画布 | `http://127.0.0.1:8901/canvas/index.html` |
| 摄影参考库 | `http://127.0.0.1:8901/photo-ref/index.html` |
| Agent 页面 | `http://127.0.0.1:8901/photo-ref/agent-page.html` |
| 3D 导演台 + 助手 | `http://127.0.0.1:8901/previs/director-agent.html` |
| 多角度（独立页） | `http://127.0.0.1:8901/canvas/multi-angle.html` |
| harness 方案对比 | `http://127.0.0.1:8901/harness_decision.html` |
| 生图参考组合 | 在画布里说「凑一组参考」→ 弹层（不是独立页） |

**改完必须加 `?nc=<随机>` 防缓存假阴性**（`AGENTS.md` 的规定）。

---

## 六、登记规则

- 新加原型文档 → 在本文档对应分区加一行
- 原型被推翻 → 不要删，移动到「已废弃」并写清被谁取代
- **单篇 ≤12KB**，超了拆主文件 + reference 子文件
