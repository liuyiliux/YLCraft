# docs/prototypes 索引

> **先看「零、原型总览」**——现在有哪几个原型、各自解决什么、最近在改什么。
> 下面是细节索引：73 份文档按主题分类，新加必须登记到这。
>
> ⚠️ **原型不是实现事实**。要落地前先看真代码，别把原型当规格。

---

## 零、原型总览（2026-11-03）

> 最近在做的是**重新设计页面原型**，所以先说清「一共有几个、各自在解决什么」。
> 下面这张表是唯一入口，其它章节都是细节。

### 现在活的原型：3 个 + 一组功能页

| # | 原型 | 入口 | 解决什么问题 | 状态 | 体量 |
|---|---|---|---|---|---|
| **1** | **画布** | `canvas/index.html` | AI 创作工作台：画布（连线图，默认）/ 镜头墙 / 素材墙（原「自由画布」，11-03 改名） | ✅ **2026-11-08 定版 · 默认带示例** | 18KB + 38 js + 8 css + 24 本地占位 SVG |
| **2** | **摄影参考库** | `photo-ref/index.html` | 摄影师的参考库（一张片子 + 偷师点）＋ 拍摄计划 | ✅ 稳定 | 424KB + 5 子页 |
| **3** | **Agent 页** | `photo-ref/agent-page.html` | 跟 AI 对话协作的三栏界面（左会话 / 中工作区 / 右产物）| ✅ 11-01 定版 | 104KB |
| **4** | **原项目功能页** | `features/index.html` | 按真实 YLCraft 功能补的页面 + 一张功能覆盖地图 | 🆕 **2026-11-08 新增** | 9 html + 1 css + 2 js |
| — | 平台壳 | `platform_shell_v17.html` | 首页 / 工作区外壳（早期形态，未继续） | ⏸ 停 | 85KB |

> 「定版」指三个活原型 + BACKLOG 10 条欠账收口，**不代表原型层不许再加页面**。
> `features/` 是按真实功能新开的覆盖缺口，见「### 原项目功能原型」一节，不算欠账、不推翻定版。

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
>
> `features/` 那组页面的单位又不一样：**一个项目 / 一份素材 / 一条任务 / 一个平台连接**。
> 它们是真实 YLCraft 的管理面，不是再做一个画布，所以独立成组、复用同一套设计令牌。

### 最近在重新设计什么（2026-11）

| 改动 | 结果 |
|---|---|
| 画布顶栏收工具 | 20 个元素 → 9 个，其余进「⋯」菜单（`77c9a70c`）|
| 镜头卡补属性 | 左下**景别**、右下**角色**，统计栏出景别分布（`8d8fdeb3` `58fcfb22`）|
| 题材区分 | 人物片（有角色/空镜）· 角色图（按角度）· 宣传片（**无角色**）（`bf2e42ff`）|
| 生图参考组合 | 不做独立页，改成画布对话里说「凑一组参考」弹出的面板（`66f80b94`)|
| 默认示例 + 占位片 | 进来就是 12 镜 / 18 节点，缩略图从纯色块换成 24 张本地 SVG 氛围片；`?empty=1` 保留真空态（2026-11-05）|
| 镜头墙铺满 | 卡片从固定 136px 改成跟视口长高 + 行间均分，12 镜不再下半屏全黑（2026-11-05）|
| 历史条折叠 | 常驻展开的历史面板会压住第二行最左卡片，改成默认只留 34px 标题条、点一下展开（2026-11-05）|
| 点节点亮连线 | 选中节点后只点亮与它直连的线（**其余保持灰色、不压暗**），相邻节点给浅青边；点空白 / Esc 取消，Shift 多选可一起亮（2026-11-07，配色按即梦收口）|
| 连线改回平滑贝塞尔 | 用户指出「主流平台不是横平竖直」：台账 21 个平台从没记过连线形态，正交折线无调研依据，是上一轮为凑「穿卡=0」自己推演的；现改回端口水平出入的三次贝塞尔（2026-11-07）|
| 连线对齐即梦（撤销避障） | 用户看即梦实拍后指出「强制不能穿图反而不好看」「点了卡片才线亮，其他时候灰色」：删掉整套走廊避障，回归单段 S 曲线直连；平时 29 条线统一灰、不分状态色，点中卡片才把直连的线点亮青，其余灰线深浅不变（2026-11-07）|
| 节点选中态改两级结构 | 用户纠正「第二张是即梦画布节点点击了以后显示的样，下面对话、上面工具」：常态卡片瘦成「图 + 标题 + 角标」，点中才在节点上方浮工具条、下方浮对话生成框；10 行参数表降为「完整参数」二级入口，右侧 420px 全局智能体栏默认收起（2026-11-08）|
| 收口第 1 批 | 追色真 0-100 程度滑杆、原图/生成图拖动对比、作品广场「复制创作画布」（2026-11-08）|
| 收口第 2 批 | 对话说「给我项目链接」→ 交**本地实例**画布卡片，点「打开画布 ↗」直接进连线图（不是云端分享，也不做复制）；说「委托它自己跑」→ 定时 + 成本上限面板（自用的保护，不是付费档位）（2026-11-08）|
| **原型定版** | 10 条欠账全销账（9 ✅ / 1 🗑 开源自用砍掉）、14 页全量复验零错、画布状态 🔧 → ✅（2026-11-08）|
| 按真实功能补页 | 盘点 `frontend/src/App.tsx` 46 页 / `main.py` 60 组路由后，新增 `features/` 一组：功能地图 + 创作项目 / 素材库 / 任务中心 / 账号中心 4 页，接进互通导航与启动页（2026-11-08）|

### 原型视觉欠账（2026-11-05 自查后的状态）

> 这里只记**原型画面**的欠账；实现侧的欠账在 `docs/research/BACKLOG.md`，别混。

| # | 事项 | 状态 |
|---|---|---|
| 1 | 默认带演示数据 | ✅ 本轮做完（12 镜 / 18 节点 / 29 连线） |
| 2 | 本地占位缩略图 | ✅ 本轮做完（24 张 SVG，三批次各一套） |
| 3 | 镜头墙铺满 + 历史条不遮卡 | ✅ 本轮顺手收掉 |
| 4 | ~~29 条连线放射穿过卡片（乱麻）~~、绿色线≠青色主色 | ✅ 2026-11-07 收口：先撤销正交方案，再按即梦实拍撤销自动避障。最终是**单段 S 形贝塞尔直连**（`routeEdge` 只算 4 个点，不采样不绕行），穿过卡片时线在节点下层被盖住；平时全灰、点卡片才亮直连线。中途的「穿卡 21 → 0 → 6」全部作废，**穿卡数不再作为验收指标** |
| 5 | ~~字号破 12px 下限~~（原默认态 146 个 <12px，最小 8px） | ✅ 2026-11-07 做完：新增 `--fz:12px`，画布主原型 6 css + 35 js + index.html 共 **601 处**统一替换；连线图 / 镜头墙 / 更多 / 模板 / 版本 / 参考弹层实测小字 **0**、文本溢出 **0** |
| 6 | ~~三个原型互不跳转、主题变量/字体栈 4 套~~ | ✅ 2026-11-07 做完：`shared/theme.css` 统一令牌（14 页共用）+ `shared/proto-nav.js` 顶栏「原型 ▾」互通菜单；**275 处 <12px 收敛到 `var(--fz)`**，字体栈统一，3D 台底色对齐。独立子页 `image-editor-v2.html` 一并并入 |
| 7 | ~~`photo-ref/favicon.ico` 404、子原型状态未登记~~ | ✅ 2026-11-07 做完：12 页补 `<link rel="icon" href="data:,">`，新增「子原型登记」表 |

> 判据只看画面：用 8901 + Chrome 无头实测。2026-11-05 那轮验 12 / 6 / 13 张卡与历史条零重叠、24 张 SVG 全 200；
> 2026-11-07 这轮验默认 18 节点 / 29 连线：中间态走过正交（穿卡 0）和曲线避障（穿卡 6），
> **终态按即梦撤销避障**：29 段 C / 0 段 L / 0 段 Q，29 条线同一个灰值；
> 点 g0 亮 3 条、点「分镜表」亮 14 条，其余线灰值不变、opacity 恒为 1；重绘 0.29ms；
> 三批次 29/17/17 条线形态一致、空态正常、零报错零 404；小字 **146 → 0**、七状态零溢出。
> 另外发现并修掉一处被字号放大暴露的老问题：`.ghint` 常驻条和 `.hint` toast 原本同贴 `bottom:8px` 叠成一团，
> 现在 toast 上移到 `bottom:58px`（聚焦提示更长，留 21px 呼吸），常驻文案也收短。
>
> 2026-11-07 晚补「节点聚焦」：`focusEdges / clearEdgeFocus` 只切 class 不重画路径，拖动、切视图、
> 断线后由 `buildEdgesSvg` + `renderGraph` 两处补回高亮（节点 DOM 重建会冲掉 `.rel`，必须补第二次）。
> 实测 13 项断言全过：点「分镜表」亮 14/29 条、点大图节点亮 3 条、选中态跨拖动与视图往返保持、
> 空白 / Esc 取消、Shift 多选亮 4 条、点连线断开仍可用、零 JS 报错零 404。
> 连线**默认不按状态分色**：29 条线统一 `rgba(255,255,255,.22)` 细 1.5px；
> 状态由节点标题小圆点与卡片文案表达，选中节点才把直连的线亮成主色青（2026-11-07 即梦规则）。

### 原型收口清单（2026-11-08，用户定方向：近期就是把原型搞完）

> **边界**：只在 `docs/prototypes/` 里把画面和交互做完整，**不接后端、不迁实现**。
> 「功能有就行」照旧 —— 原型证明的是形态，不是功能验收。
> **产品定位（2026-11-08 用户明确）**：**开源自用**，不做付费档位 / 商业化分级。
> 但「调模型要花钱 → 门禁批准」「积分 / 成本上限」是自用也真实的 API 成本与保护，**保留**；
> 成本记账 ≠ 卖档位，别一刀切删。

**「搞完」= 四条判据，2026-11-08 17:50 全部成立 → 原型定版**：

1. ✅ 三个活原型 + 启动页 + 在用 🟡 子原型画面定版、顶栏互通可达（14 页复验全过）；
2. ✅ BACKLOG 第五节 **10 条欠账全销账**：9 条 ✅、1 条 🗑 写明理由砍掉，无 🔲；
3. ✅ 全量 14 页复验：零可见小字、零文字裁切、零 404、零 JS 报错；
4. ✅ 画布状态改为 ✅ 定版，并写清「能演什么 / 不能证明什么」（见下节）。

**10 条欠账终态**（画面核销结果见 BACKLOG 第五节，别再凭 grep 判断有没有做）：

| 批次 | 欠账 | 状态 |
| --- | --- | --- |
| 第 1 批 · 补齐半缺 | ⑤ 追色面板补真 0-100 程度滑杆 | ✅ 11-08 做完 |
| | ⑥ 原图 / 生成图并排或拖动对比入口 | ✅ 11-08 做完 |
| | ⑧ 作品广场 + 「复制创作画布」 | ✅ 11-08 做完 |
| 第 2 批 · 补真缺 | ⑨ Agent 返回 `projectUrl` 可接管 | ✅ 11-08 做完 |
| | ⑩ 设计委托（定时 + 积分 / 成本上限） | ✅ 11-08 做完 |
| | ~~② 排队免费 / 加速付费两档~~ | 🗑 **砍**（开源自用，没有付费档位） |
| 第 3 批 · 定版 | 全量复验 + 文档定版 + 提交 | ✅ 11-08 做完 |

**第 1 批落地（2026-11-08）**：新增 `canvas/js/37-compare.js`、`canvas/css/08-finish.css`；
改 `25-enhance.js`（追色真滑杆，追场景模式禁用）、`07-agent.js`（模板弹窗加作品广场 Tab，
按复制次数降序，`clonePlaza()` 克隆画布且不挂模板快照）、`36-nodeworkbench.js`（图片工具条加「对比」）、
`35-infinite.js`（`.cmp-ov` 不算画布背景）、`index.html`（引新文件 + 47 处 `?v` bump 到 `202611081620`）。

> 验收：8901 + 无头 Chrome 1440×900 —— 滑杆 70→35 数值与 `--deg` 同步、追场景自动禁用；
> 对比分割 50%→25%、并排切换、Esc 关闭；广场 4 张卡 / 4 个复制按钮 / 复制后 12 镜回写；
> 4 个关键页零可见小字、零 JS 报错、零 404。截图 `_ui_compare/batch1-*.png`。
> 溢出检查报的 `.gnode` 是端口 `.gport` 故意外伸 3px（量过几何），不是文字裁切。

**第 2 批落地（2026-11-08）**：新增 `canvas/js/38-delegate.js`；改 `07-agent.js`（对话路由加 ⑨/⑩
触发词、`agDeliverCanvas()` 交付画布卡片、`takeoverCanvas()` 真切换画布）、`08-finish.css`
（`.dl-*` / `.dg-*`）、`index.html`（顶栏「委托」+ 引 38 + 48 处 `?v` bump 到 `202611081750`，18:45 纠偏后再 bump 到 `202611081845`）、
`35-infinite.js`（`.dg-ov` 不算背景）。
- **⑨ 口径**：`projectUrl` 是**本机实例地址**，不是云端分享链接；卡片带节点 / 连线 / 镜数、
  「本地实例」角标和一行**只读地址**。开源自用只有一个实例，2026-11-08 用户纠偏后
  **删掉「复制链接」**：只留一个「打开画布 ↗」按钮，点一下落到 `flow + graph` 连线图、
  收起右侧智能体栏、顶栏变「已打开」。对话说「给我项目链接 / 接管 / 建个画布」即触发。
- **⑩ 口径**：定时 + 上限是**自用的无人值守与成本保护**，不是付费档位；委托是排程规则，
  与任务中心里的单次生成任务分开；原型不真跑、不扣积分、不上传。

> 验收：卡片 URL 为 `http://127.0.0.1:8901/canvas/index.html?canvas=…`、**只有 1 个「打开画布 ↗」按钮、页面无「复制链接」字样**；
> 点后 `mode=flow` / `flowView=graph`、18 节点 29 连线、右栏收起、顶栏变「已打开」；
> 委托 3 任务 / 3 时间 / 上限 40 触发「超过上限，到上限就会停」，提交后 Agent 消息写明
> 「不会真的定时执行」、记录可撤销、Esc 关闭。截图 `_ui_compare/batch2-*.png`。

**第 3 批 · 14 页全量复验**：启动页 / 画布 / 摄影库 / Agent 页 / 3D 导演台 / 修图器 v2 /
摄影库 4 子页 / 修图器 v1 / 多角度 / 局部重绘测试页 / harness 结论页 ——
零可见小字、零 404、零 JS 报错、零文字裁切。
溢出检查里 4 处既有差异量过几何，全不是文字裁切：`.gnode` 端口外伸 3px、
`.fig` 小人手臂 4px、`.sitem-t` 单行省略号（刻意 ellipsis）、`section.hero` 装饰层与 `input` 内部布局，别去「修」它们。

### 原型能演什么 / 不能证明什么（定版边界）

| 能演 | 不能证明 |
| --- | --- |
| 三套界面的信息结构、两级选中态、工具条 / 对话框的位置关系 | 真模型生成、真像素、真扣费、真定时调度 |
| 12 镜 / 18 节点 / 29 连线示例，缩放、拖动、小地图、版本记录 | 刷新后状态不丢（内存态）、并发 / 失败 / 重试语义 |
| 门禁「花钱前批准」、任务模拟推进、交付检查拦住占位产出 | 服务端强制门禁、真实供应商全链路 |
| 复制创作画布、Agent 交付本地画布链接、委托排程 | 画布文档真复制、project id 鉴权、外部分享 |
| 三主题（deep / moonlight / dawn）与 14 页互通导航 | 移动端真机手感、无障碍、性能 |

> 一句话：**这一版是设计稿，不是功能验收**。真实现要逐项接后端，迁移时看真代码，别把原型当规格。

> 原本就完成、不用再动：① 小地图 / 版本记录、③ 追色决策表、④ 保存为新图层、⑦ 批量应用（`22-batch.js`）。
> `CANVAS_CURRENT_STATE.md` 与 `PROTOTYPE_REMAINING_SCOPE.md` 里的数字和「已做/未做」均已过期，别当当前事实。

### 原项目功能原型（2026-11-08 新增）

> 起因：用户要求「看原来 YLCraft 的功能，再在原型上新加符合的样式页面」。
> 盘点发现真实实现有 **46 个前端页面**（`frontend/src/App.tsx`）、**60 组后端路由**
> （`backend/app/main.py`）、33 份规格，而三个活原型只覆盖中间的摄影 → 画布 → Agent 一段。
> 于是先补主链路四页，**视觉完全沿用 `shared/theme.css` + 深色令牌，不另造一套**。

| 页面 | 对应真实功能 | 画面上的单位 |
|---|---|---|
| `features/index.html` | 功能覆盖地图（真实功能 → 原型覆盖 → 待补） | 一个功能域 |
| `features/gen-wall.html` | `/image-gen` `/video-gen` `/model-3d` 生成结果墙（2026-11-20 新增） | 一次生成（三页结果区形态并排对照） |
| `features/characters.html` | `/characters` 角色库（2026-11-20 新增并重做） | 一个角色（角色册 → 三栏详情 → 折叠面板 / 自定义标签 / 世界使用） |
| `features/story-desk.html` | `/story` 创作项目 | 一个项目的生产阶段 |
| `features/assets-home.html` | `/assets` 的工作台首页（2026-11-20 新增） | 整个素材库的状态（时间 / 统计 / 7 天导入趋势 / 整理概览 / 最近导入） |
| `features/assets.html` | `/assets` 资产中枢 | 一份素材（含版本 / 血缘） |
| `features/tasks.html` | `/tasks` 任务中心三 Tab | 一条任务（含诊断 / 事件 / 日志） |
| `features/accounts.html` | `/accounts` 平台连接 | 一个平台连接 |

**共享骨架**：`features/app.css`（颜色、卡片、Tab、表格、时间线、弹层、toast）
+ `features/app.js`（toast / Tab / Esc 关弹层）。每页数据与交互写在自己 html 里，
不建第二个框架。所有可见文字 ≥ `var(--fz)` 12px；失败原因说人话、不甩字段与堆栈；
界面负责事实（状态、诊断、出处），不冒充对话；「不适用」与「没有」分开写。

**边界**：示例数据全在本地，不请求后端、不真生成、不真扣费、二维码不可真扫。
真实实现里**没有独立页面**的「成本 / 配额」「独立知识库」「监控大盘」没有被编造成已有功能补进来。
下一批候选：采集下载发布、设置与 AI 连接器（AI 生成结果墙、角色工作台均已于 11-20 补完）。

**角色工作台的形态按真实页面 + 规格来**（证据：`frontend/src/pages/character-detail/index.tsx`、
`openspec/specs/character-management-redesign/spec.md`、`docs/research/2026-10-20_workrally_manju_pipeline.md` 等）：
名册卡带完善度 9 项（外貌/性格/背景/年龄/身份/弧光/立绘/音色/视觉资产），<50% 弱化；
详情两栏（左视觉参考 + 版本、右 Bible 带 `original/ai_inferred/unset` 来源标记）；
关系圆形布局 hover 高亮边；世界视角显式列出被改写的字段；Prompt 资产包四项带复制；
独立「一致性巡检」扫一整套图并定位到具体图的具体部分（借 Lovart/Arti）。
**语义写死**：脸按角色档案锁死、不进随机池，指定角色 ≠ 随机人设，换的是衣橱不是脸；
  「龙」这类非人角色按「跨镜头复现」判据入库。飞书分享链接（`basevibe`）实际是一个亮色**资源库索引页**
  （81 条开源项目 / 工具 / 教程，内容在 iframe 里），只借了「统计数字 + chips 筛选 + 清爽卡片」的概览观感，
  **不是**角色工作台设计依据；但它收录的项目给了两条实质补充：
  `character-design-sheet` 的**一致性强度梯度**（LoRA > 角色卡锚点 > 同种子+相似提示词 > 图生图精修 >
  提示词放参考图）已做成原型里可见的 5 行梯度表，本项目定位在「角色卡 Bible（中高、成本低）」；
  `MOKEAIGC` 明确「不做单个角色身份档案」，反衬角色库的必要性。

**11-20 晚按用户提供的真实页面截图重做**（之前那版照规格搭，缺了真实页面的主体）：
用户指出「和原来比少了好多功能」，对照后确认缺三栏中间的「图像提示」栏、真实 Bible 字段组、
整个「自定义标签」视图、世界使用、顶部状态与操作按钮、立绘配置条。重做的依据不是猜字段，而是
两份设计文档：**「屏幕上收、纸上全展开」**（长面板收进 `<details>`）、**「视觉卡是 source of truth」**
（结构化字段生成可复制 prompt，不让用户先写巨型提示词）、**`identity_board_16_9`**
（左 1/4 身份锚点 + 右 3/4 三视图/姿态/表情/细节）。现在页面两个视图：
「角色详情」（角色册 4 筛选 + 状态标签 + 立绘配置条 + 三栏 + 折叠面板）、
「自定义标签」（10 个折叠分组 + 世界使用 3 卡带编辑/删除/打开世界项目按钮）。

**11-20 晚再按真实截图收版式**（用户说「感觉还没原版好看」）：差距不是字段少，是气质错——
之前自己加了 hero 大标题 + 4 个统计数字 + 给每块套卡片，把原版的**克制感**冲掉了。
按原版重排：角色栏收窄到 190px 且两个视图**共用**（ sticky 常驻，切视图仍可换角色）、
详情三栏用 1px 竖线分隔不再套大卡、自定义标签改双列细线折叠、世界使用移到下方卡片只占左侧 380px
（右侧留白）、**删掉 hero 统计卡与底部长说明**。字段与交互一个没删（6 角色 / 8 Bible 字段 /
4 筛选 / 23 折叠 / 关系图 6 节点 5 边 / 3 世界卡）。
再把详情底部 13 条折叠面板按内容宽度分流：**宽内容（人物摘要 / 关系 / 一致性方案 / Prompt 包 / 巡检）通栏，
只有一行字段的 8 个短面板双列细线**（每列 4 个，和自定义标签同一套节奏），
  不是为了「全双列」把关系图和梯度表挤窄。
**11-20 再调三栏与版面**（用户「主图占位大一点、右边再往右、整体偏左」）：量了几何后确认
根因是 `.page.wide` 宽屏下卡在 1680px 居中、两侧各留 120px，而主图栏只有 390px。改成本页
`max-width:1880px`、`.tri3` 列权重 `1.16fr/1.04fr/1fr`、`.pmain` 由 4:3 改 4:5 竖幅
（1440 下主图 363×272 → 407×509，1920 下 567×708，Bible 栏右边缘贴到 1869/1920）。
**11-20 再收右下角空洞**（用户「右下角有点空？」）：量出三栏被主图拉成等高 744px、
右栏 Bible 只有 303px，硬撑 441px 空槽。三处收口：主图加 `max-height:440px`（三栏降到 676px，
主图仍比原 272px 高一截）、Bible 行加细虚线与呼吸、右栏补「档案完整度 8/9 + 进度条 +
原文/AI推断/待确认图例 + 待补项 + AI 补全」并由 Bible 字段与来源标记**同源计算**（与角色列表
「缺 N 项」对得上），中栏补「出图参数（负向词/画幅/seed）」；「最近切镜 / 字段来源 / 一致性状态」
从底部折叠面板挪进 Bible 栏底部（避免右栏空 + 同信息两处），详情折叠面板 23 → 21。
验收 `ylcraft_verify_chars2.py` + `ylcraft_verify_font13.py`：22 页 × 1440/1920 零小字/溢出/404/报错；
`?v` 终值 `202611201930`。截图 `colfoot-3-1440x900.png`。

**11-20 收顶部信息块，让主图进首屏**（用户「这块有点占地方，打开第一眼要看到主图」）：
顶部原来堆了三层（身份两行 48 + 立绘配置条 41 + 世界视角 85 ≈ 150px），把主图压到 y≈300。
按 Linear / Figma 详情页的做法收成两行：**身份行 35px**（名字 15px + 4 个状态标签 19px 高 +
右侧 4 个操作，标签与按钮同一基线）、**世界视角行 39px**（3 个 chip 24px 高，选了世界就直接把
5 个覆盖项作为黄标签排在 chip 后面，说明压成一个 `?` 圆点 toast，不再常驻两行说明段）。
「立绘生成」不再单独占一条，并进中栏**出图参数**（性能组双模型 / 尺寸 + 随机生成开关 / 负向词 /
画幅 / seed），中栏因此成为一条完整出图表单：提示词 → 参数 → 视角生图。
主图 y 从 ≈300 → **229**，且 `.tri3` 左栏定宽 440px、`.pmain` 去掉 `max-height` 只留 `aspect-ratio:4/5`
（1440/1920 都是 411×514，竖幅不再被横向裁切）。空出来的右栏下部补**「出场镜头 4 行」**
（第 2/5/8 镜 + 广告版，带 一致 / 脸漂 / 多配饰 状态），三栏底部齐在 942px 附近，不留空槽。
顺手修了个老 bug：视图 Tab 也带 `data-v`（tags/detail），与立绘版本按钮的 `data-v`（0..3）撞了，
点 Tab 会 `VERS[NaN].img` 报错 —— 事件改成限定 `#vers [data-v]`。

**11-20 末再按原版比例收三栏**（用户「左边太挤了 右边太空了 看看原来的设计」）：
先回真实前端找依据 —— `character-detail/styles.css` 的「视觉中心区三段布局」注释写的是
「主视图 / 视图矩阵 / Bible 横向铺满，避免宽屏右侧留白」，实现是 `.cd-hero-main{flex:1.35;max-width:660}`、
`.cd-hero-matrix{flex:1;min-width:200}`、**`.cd-hero-bible{flex:0 0 320px}`**，外壳
`.character-detail-shell{max-width:1600px}`（内含 260 侧栏 → 内容 1322）。
我之前三列都给了 `1fr`，1920 下 Bible 被拉到 599 宽，值又是短词，右边半列全是空行；
中栏（身份板那条）只有 599，`左 1/4` 身份区的文案全在折行。改成
**`460px / minmax(0,1fr) / 336px`**（对应原版 主视图 / 矩阵 / Bible 320），
本页 `max-width` 由 1880 收到 **1720**（侧栏 190 与原版 260 等比换算），1440 下 460/402/336、
1920 下 460/682/336，宽屏两侧各留 100px 而不是把三栏摊开。
窄屏再加一层 clamp：`clamp(380px,32vw,460px)` / `clamp(300px,24vw,336px)`，1300 下 416/330/312 不塌。
**顺带把右栏的数据口径改成自洽**：空值一律挂「未设置」徽标（原来薄角色的值是「—」却仍标「原文」，
出现「0/9 但原文 3」），完整度/图例/待补三处同一套判据，待补超过 3 项显示「等 N 项」；
「出场镜头」从静态 4 行改成按角色渲染（薄角色显示 0 + 「还没进过镜头 · 从分镜里引入」），
不给没有立绘的角色编「一致」状态。验收 `verify_chars2` + `verify_font13` 均 OK，
双宽零小字/溢出/404/报错，交互 7 步 0 报错。

**11-20 晚把「提示词预设」做成真能切的**（用户「这个提示词怎么切换的，主视图/三视图/九宫格应该不一样吧」）：
原来中栏只有一个写死的 16:9 身份板 prompt，所有按钮都出这一句。真项目不是这样 ——
`backend/app/services/character/portrait_prompt.py` 里 `PORTRAIT_PRESETS` 有 13 个 preset、
每个自带 `intent` 段落和 `PRESET_NEGATIVE_CONSTRAINTS`，由
`POST /api/v1/characters/{id}/portrait/prompt-preview` 的 `preset` 参数切换。
中栏按这条链路补了 5 个 tab（主视图 `main_portrait` / 三视图 `multi_view_sheet` /
设定板 `character_sheet_16_9` / 身份板 `identity_board_16_9` / 九宫格，内层再分
`expression_grid_3x3` 与 `pose_grid_3x3`）。切换时**同时换五样东西**，不是只换标题：
① 示意图（单张 / 正侧背三格 / 34%+66% 设定板 / 摘要板 / 3×3 九格带格子名）；
② 提示词正文（意图段落 + 同一套角色字段，行数 13–15）；
③ 负向词（各 preset 专属，如九宫格「非九宫格、人物跨格、表情重复」）；
④ 画幅与尺寸（4:5 1024×1280 / 16:9 1536×864 / 1:1 1536×1536）；
⑤ 按钮文案（出主视图 / 出三视图 / 出设定板 / 出身份板 / 出九宫格）与 toast。
**顺手纠了口径**：`identity_board_16_9` 在 v2 已 re-scope 成「摘要板，不作为作画生产基准」
（tasks.md 2.12），原型里那张「左 1/4 身份区 + 右 3/4 三视图」其实是 `character_sheet_16_9` 的版式，
现在两套分开画，身份板按 v2 的「信息区 + 主立绘 + 缩略预览」重画。
九宫格按后端 9 格固定映射写（表情：中性/微笑/愤怒/悲伤/震惊/害羞/疑惑/冷笑/哭泣；
动作：自然站立/双手插兜/双臂交叉/整理领带/单手示意/双手背后/微微侧身/回头站姿/近景动作），
并保留后端那句「不建议作为第一张锁脸图，有主视图 / 三视图时以参考图优先」。
示意图在宽栏里加了 max-width（三视图 470、九宫格 330），否则 1920 下会把参数挤到首屏外。
再补**反向对应**：左侧「角色视觉参考」的主图右上与 4 个版本缩略图都加了 preset 角标
（主视图 / 三视图），点某个版本时中栏自动切到「出这张图的那条 preset」，`#verInfo` 写成
`当前：雨夜版 · 主视图 · 雨夜之城覆盖`（版本名与前缀重复时不写两遍）。
这样一个角色身上「哪张图来自哪条提示词」是同一条线，不用靠记忆。

**11-21 夜修主题按钮**（用户截图「这个没跟着主题颜色走的」）：`proto-nav.js` 的「原型 ▾」和
`theme-switch.js` 的「晨曦 ▾」原来把深色写死在注入样式里，dawn 亮色下页面白了、按钮还是黑胶囊。
改成两套变量方案：`theme-switch.js` 只服务 features 页，直接读页面 `--s2/--ln2/--tx/--ac/--modal`；
`proto-nav.js` 横跨画布 / 摄影库 / features 三套不同命名的变量，自带 `--yl-*` 一组，
用 `:root[data-theme=...]` 与 `body[data-t=...]`（摄影库把主题挂 body 上）双选择器切换。
实测 dawn 下两个按钮都是白底深字（原型 rgb(255,255,255)/rgb(39,39,42)，
晨曦按钮 rgb(250,250,249)/rgb(39,39,42)），菜单同步变浅；月光紫 `#a78bfa` 也跟着走；
画布页不引主题开关、没有 data-theme，按钮仍是原深色。全站 `?v` 终值 `202611212325`（110 处）。

**11-22 凌晨修 hero 主题**（用户「我说的不是按钮，是中部上面这里」）：功能地图页顶部那块
「原型功能 → 原型页面」hero 背景写死 `linear-gradient(#14141a,#0f0f12)`，dawn 下正文走
`--tx2` 变深、背景还是黑，整块糊掉。背景改 `linear-gradient(120deg,var(--greet),var(--s1) 62%)`，
并删掉正文里「沿用画布那套**深色**令牌」的过时说法。顺手把同类的两处写死深色改掉：
`tasks.html` 的日志区 `#0b0b0e` → `var(--s2)`，`assets.html` 底部批量条 `#1b1b22` → `var(--modal)`、
阴影 → `var(--shade)`；`accounts.html` 的二维码白底是功能需要，保留。
实测 dawn 下 hero 是淡墨绿→白的浅底、文字 `rgb(39,39,42)`；deep 下仍是深绿→深灰，
`verify_font13` / `verify_theme` / `verify_chars2` 全过，`?v` 终值 `202611220022`。

**AI 生成结果墙的形态按真实前端来，不硬塞成一个网格**（调研见 2026-11-20 日志）：
生图页结果区是响应式**网格卡**（prompt 30 字 + provider + 已回写 + seed），
视频页是 **Timeline 列表**（状态 / provider / 时长+比例 / 进度 / 错误，最多 10 条），
3D 页是**网格 + 独立「生成历史」Tab**（静态 / 已绑骨 / 带动画筛选）。
成本金额、帧率、耗时、人民币价格**没有画上去**——真实前端没渲染这些字段
（后端返回有 `cost` 不等于页面有）；生成端点写当前真实路径，
遗留的 `/3d/generate-from-image`（TripoSR）只在脚注提，不混进当前页。

> 验收（2026-11-08 19:30，8901 + 无头 Chrome 1440×900）：启动页 / 功能地图 / 4 功能页 / 画布
> 共 7 页零可见小字、零文字溢出、零 404、零 JS 报错；互通导航 12 条链接（含 5 个 `features/`）、
> 跳转与当前页高亮正常。逐页交互断言全过：创作项目 5 阶段 / 12 章 / 6 分镜图 / 采纳 / 门禁；
> 素材库 12 图加载 / 筛选 / 搜索 / 版本时间线 / 批量 / 列表视图；任务中心三 Tab / 重试 / 诊断 / Esc；
> 账号中心 6 卡 / 启停 / 体检 / 扫码 3 步 / 缓存清理。截图 `_ui_compare/feat-*.png`。
> 改了 `shared/proto-nav.js`，按门禁把 14 个在用原型的 `?v` 统一 bump 到 `202611081920`（73 处），
> 历史 `canvas_*.html` / `platform_shell_*` 没碰。

### 2026-11-20 按 modern-web-guidance 收口（只动 features/ 5 页）

> 用户提供 `C:\Users\zhouxiang\.codebuddy\skills\modern-web-guidance`。它是**现代 Web 最佳实践
> 检索器，不是视觉风格包**：要求写 HTML/CSS/客户端 JS 前先 `search` + `retrieve`，改完对照指南核验。
> 本机 Node 22.22.2，可直接跑本地 `modern-web.mjs`，无需联网 `npx`。

按检索结果把这 5 页里手搓的原语换成平台原生做法（**视觉没变，只改语义与实现**）：

| 之前 | 现在 | 指南 |
|---|---|---|
| 手写 `.ov` 遮罩 + 自己绑 Esc + 自己关 | 原生 `<dialog>` + `showModal()` + `closedby="any"`，不支持 `closedby` 时走点击坐标 fallback；`::backdrop` / `overscroll-behavior` | `dialog` / `light-dismiss-a-dialog` |
| Tab 靠 `.on` class、选中态改颜色和字重 | `role=tablist/tab/tabpanel` + `aria-selected` 唯一状态源 + `hidden="until-found"` + 方向键 + 伪元素下划线 | `tabs` |
| 启停用 `<button class="sw">` | `<input type="checkbox" switch role="switch">` + `<label>`，`change` 同步 `aria-checked`；离线原型用内联轻量 fallback，不引 npm polyfill | `switch` |
| 5 页硬编码深色，无 `color-scheme` | `<meta name="color-scheme" content="dark">` + `:root{color-scheme:dark}`，滚动条 / 下拉等原生 UI 跟随 | `dark-mode` |
| 表格无 `caption` / `scope`，筛选框只有 `aria-label` | 表格 `caption` + `th scope=col` + `role=region tabindex=0` 容器；筛选框改成 `<label for>` + `type=search` | `responsive-table` / `accessibility` / `forms` |

> 验收（`ylcraft_verify_mwg.py`，8901 + 无头 Chrome 1440×900）：7 页零可见小字、零溢出、零 404、
> 零 JS 报错；5 页 `color-scheme` 计算值均为 `dark`；Tab 方向键 `aria-selected` 同步、
> 初始 1 选中 / 2 个 `until-found` 面板；任务诊断与扫码弹层 `matches(':modal')` 为真、
> `aria-labelledby` 有效、Esc 关闭且焦点回到触发按钮；6 个开关 `role=switch`、键盘 Space
> `aria-checked` true→false；表格 `caption` / `th[scope=col]` 齐全。截图 `_ui_compare/mwg-*.png`。
>
> 本轮改 `features/app.css` + `features/app.js` + 5 个 html，按门禁把 19 个在用页面的 `?v`
> 统一 bump 到 `202611201225`（93 处）；**其它 14 页只是版本号跟着换，代码与画面没动**，
> `shared/theme.css` / `shared/proto-nav.js` 也没改。

### 2026-11-20 下午 · 素材工作台首页（参考第三方图的信息结构，不抄配色）

> 用户给了一张别人的素材管理截图，问「属于什么风格」。判断：那是**素材库的工作台首页**
> （单位是整个库的状态），不是素材列表页（单位是一份素材）；视觉是深墨绿 + 荧光黄绿的
> 个人工作台卡片仪表盘。用户选 A：**照信息结构补一页，保留我们的青色令牌**。

| 参考图的信息块 | 我们的落地 |
|---|---|
| 时间问候大卡 + 弧线装饰 | `#gClock` 每秒走时 + 日期 / 农历 / 问候按时段变 + 分类 chips 可下钻 |
| 分类统计甜甜圈 | `conic-gradient` 圆环 + 图例（图片 520 / 视频 22 / 音频 108 / 字体 0 / 剪辑工程 1），带 `role=img` 文字替代 |
| 月历 + 农历标记 | 2026-11 真实日历（JS 按 `getDay()` 排），19/20/26 有标记、20 高亮、点日期切换；`‹/今天/›` 可翻月 |
| 快速启动彩色图标 | 10 个本地色块图标（WPS / Chrome / 微信等），点只提示「原型不真打开」 |
| 整理概览三数字 | 531 未分类 / 651 未标记 / 0 重复，附「去补标签」入口 |
| 最近导入 + 搜索列表 | 5 项最近导入；底部 6 行素材表（caption + scope + 键盘可滚容器）、搜索真过滤、分类下钻真按 `?type=` 筛 |

**不是抄视觉**：配色仍走 `shared/theme.css` 的青色 `--ac`，三张大卡 / 三张小卡 / 底部列表的骨架
与其余功能页一致；原型不联网、不读磁盘，快捷启动 / 导入 / 添加文件都只演示入口。

> 验收（`ylcraft_verify_home.py`，1440×900）：3+3 张卡一屏内、时钟跳秒、日历 30 天 / 5 个标记 /
> 选中态、10 图标 + 5 最近导入 + 6 行表、搜索 2/0 行与空态；点「视频 22」下钻到 `assets.html?type=视频`
> 真筛出 2 张卡且「视频」chip 高亮；导航 13 链接含新页；零小字 / 溢出 / 404 / JS 报错。
> `?v` 终值 `202611201445`。截图 `_ui_compare/home-*.png`。

### 2026-11-20 晚 · 工作台去装饰 + features 三主题开关

> 用户看完首页反馈「日历没啥用、快速启动得想想有没有用、亮色什么样、应该能切主题」。
> 三项都按推荐收：日历 → 最近 7 天导入趋势（**点某天真筛**），外部 App 启动 → 四件常用动作，
> features 6 页加三主题开关（命名对齐摄影库 deep / moonlight / dawn）。

| 块 | 之前 | 现在 |
|---|---|---|
| 第三张大卡 | 11 月日历 + 农历 / 节日标记（跟素材无关） | 7 天导入柱状图，共 57 份、今天高亮；点某天跳 `assets.html?day=11-18`，素材库认 `day` 参数、显示「11 月 18 日导入」chip、只出当天 2 张 |
| 快速启动 | 10 个 WPS / Chrome / 微信色块（点了只 toast「不真打开」） | 4 件常用动作：添加文件 / 从画布送入 / 补标签 531 / 去采集，前三个真跳对应页 |

**主题开关**：新增 `features/theme-switch.js`，挂在 6 页顶栏「主题 ▾」，三套配色集中在
`features/app.css` 的 `:root[data-theme]`（deep 默认 / moonlight 紫 / dawn 亮）。选择记
`localStorage['ylcraft-features-theme']`，刷新保持；`meta[name=color-scheme]` 跟着切
（dawn = light，其余 dark），原生滚动条 / 表单不白闪。面板固定深色（同 `proto-nav.js`），亮色下可读。
**画布页不引入开关**：它大量用 `rgba(255,255,255,x)` 画连线 / 文字，亮底会消失——实测画布页
开关 0 个、无 `data-theme`，不受影响。三套主题都对齐摄影库同名主题，但各页变量体系独立。

> 验收（`ylcraft_verify_theme.py`，1440×900）：6 页 × 三主题零小字 / 溢出 / 404 / JS 报错；
> 切换后 `data-theme` / `color-scheme` / 实际背景色三者一致（deep `rgb(8,8,10)`、moonlight
> `rgb(13,11,16)`、dawn `rgb(248,247,244)`）；刷新保持、方向键 + Enter 可切、菜单 `aria-checked` 唯一；
> 趋势 7 柱 / 点 11-18 跳素材库出 2 张 / 清空回 12；画布页无污染。
> `?v` 终值 `202611201530`（103 处）。截图 `_ui_compare/theme-*.png`。

### 节点选中态：两级信息结构（2026-11-08）

> 起因是四张即梦截图。**图 2 不是另一个页面，是同一个画布点中节点之后的状态**——
> 上一轮把它当「图片编辑页」排除掉，跑去建议改 3×4 网格，靶子整个错了。
> 即梦更好的不是「稀疏」，是**常态极简、选中才展开**的两级结构。

| 状态 | 卡片 / 浮层 |
|---|---|
| 常态 | 图 + 分镜标题 + 图上角标（左下景别、右上时长 / 分辨率），**不常驻运行按钮、不默认弹参数表** |
| 选中 | 节点**上方**浮按类型区分的工具条（生图 / 视频 / 3D / 文本各一套 + 完整参数 + 运行 + 关闭），**下方**浮对话生成框（相机 / 配色 / 风格 / 景别 chips + 提示词 + 模型 / 比例 + 发送），节点本体留在中间 |
| 二级 | 原来那张 10 行字段的 `gparams` 只在点「完整参数」时出现；跑完节点也不自动弹回来 |
| 全局 | 右侧 420px 智能体栏**默认收起**成 34px 竖条，点开仍是全局对话（`send()` / `agAdd()` 全保留）。它是全局对话，跟节点级「下对话框」是两件事 |

实现：`canvas/js/36-nodeworkbench.js` + `canvas/css/07-nodeworkbench.css`；接线在
`02-canvas.js`（选中 / Shift 多选 / 切视图 / 空白与 Esc 关闭）、`05-account.js`（跑完不自动弹参数表）、
`35-infinite.js`（浮层与竖条不算背景，别触发平移）。浮层挂 `body` 用 `fixed` 定位并逐帧量节点屏幕坐标，
**不挂 `.ginner`**——那块会被整体 `scale`，挂进去工具字会缩破 12px 下限。

> 实测（8901 + Chrome 无头，1440×900）：点 `g4`，工具条底边在节点上沿上方 10px、
> 对话框顶边在节点下沿下方 10px，两者都在画布可视区内；Ctrl+滚轮缩到 112% 后间距仍是 10/10。
> 默认 18 节点 / 29 连线 / 12 个图内角标、常驻运行按钮 0、参数表 hidden、亮线 0；
> 选中亮 2 条直连线。完整参数开关、发送（同步留一份到全局对话）、智能体展开 420px / 收起、
> 空白 / Esc 取消全过；新 UI 可见小字 **0**、溢出 **0**、404 **0**、JS 报错 **0**。
> 本轮 `?v` 终值 `202611080035`。**网格和 12 镜大图卡尺寸没动**。

### 跨页一致性 · 子原型登记（2026-11-07 ⑥⑦）

> **共享文件就两个**，14 个活/子原型 + 5 个 `features/` 功能页共同引入，历史版本一律没碰：
>
> | 文件 | 作用 |
> |---|---|
> | `shared/theme.css` | 通用令牌：`--fs` / `--fm` / `--fz:13px` / `--bg` / `--ac`。各页先引它、再写自己的 `<style>` |
> | `shared/proto-nav.js` | 顶栏「原型 ▾」互通菜单（总览 / 画布 / 摄影库 / Agent / 子原型 / `features/` 5 页），从 script src 反推站点根，各层子目录都能用；没顶栏的页自动退到右下角 |

**先纠正一条自查误判**：摄影参考库**不是「没有 CSS 变量」**。它有一套对齐真实
`theme.tsx` 的三主题体系（`[data-t]` = deep / moonlight / dawn），字号下限本来就是 12px
（`--fs-xs`）。四页主色其实都是 `#22d3ee`，差异主要在变量命名（`--ac` vs `--pri`）
和散落的小字。所以这轮**没有拍平主题**：只把摄影库 `--ff` 指到 `--fs`、
`--fs-xs` 指到 `--fz`，**颜色变量一个没动** —— 拍平成单主题会让亮色 dawn 里的
白字 / 白边消失（记忆里踩过的坑）。

> **2026-11-20 字号下限 12 → 13px**：用户反馈「字体是不是有点小」。先量了 10 页，结论是
> **全站正文本来就都是 12px**（角色库 97% 文本压在下限，连角色名和分区标题也是 12px），
> 显得小是因为缺层级、不是字号不统一。用户仍要全站上调，于是 `--fz:13px` 改一次、
> 22 页 113 处 `?v` 一起 bump。**摄影库 booklet 等 5 个子页当时漏改**（只有主页把
> `--fs-xs` 指到 `--fz`，子页仍硬编码 12px），这次一并统一；`--fs-body:16 / --fs-cap:14 /
> --fs-sm:13` 与三主题颜色不动。shared/proto-nav.js、features/theme-switch.js 里注入的
> 「原型 ▾」「深海 ▾」按钮也原为 UA 默认 12px，一并走 `var(--fz)`。
> 验收脚本小字判据同步从 `<12` 提到 `<13`：**22 页 × 1440/1920 双宽零小字、零溢出、
> 零 404、零 JS 报错**。两处 13px 挤出来的真溢出已修（gen-wall 生图卡「复制提示词」→「复制」，
> 卡片内宽只有 159px；`.gcard .ops .btn` 加 `min-width:0`）；previs `.fig` 那 4px 是装饰
> 手臂 `right:-4px` 外伸，不是文字裁切，进白名单。

真正收掉的是三件事：
- **字号**：14 页共 **275 处 `<12px` → `var(--fz)`**（Agent 95 / 3D 台 50 / 摄影库 36 /
  修图器 v2 32 / 启动页 5 等）；画布自己那份重复的 `--fs/--fm/--fz` 定义也删了，
  由共享文件唯一提供。实测 14 页可见小字 **全 0**、文本溢出 **0**。
- **互通**：三个活原型之前只有启动页是枢纽，现在每页顶栏都有「原型 ▾」，
  点击展开 7 个链接、当前页高亮、Esc / 点外部关闭。菜单面板自带固定深色底，
  **不读页面主题变量**，亮色 dawn 下实测仍可读。
- **零碎**：12 页补空 favicon 消 404；3D 台底色 `#06070a → #08080a`。

**子原型登记**（只有标 🟡 的还在用，其余别当规格）：

| 页面 | 单位 / 用途 | 状态 |
|---|---|---|
| `previs/director-agent.html` | 3D 场景 + 运镜 + 助手 | 🟡 子原型 · 完成度比启动页标的「子原型」高，见 `PREVIS_AGENT_V1.md` |
| `canvas/image-editor-v2.html` | 一张图的图层 / 参数 / AI 建议 | 🟡 子原型 · 字号已并入 `--fz` |
| `photo-ref/booklet.html` / `onsite.html` / `light-api.html` / `model-profile.html` | 作品册 / 现场 / 光线 / 模特档案 | 🟡 摄影库子页 |
| `canvas/image-editor.html` | 修图器 v1 | ⏸ 参考 · 被 v2 取代 |
| `canvas/multi-angle.html` | 一个角色的多角度图 | ⏸ 参考 · 已并入 Agent 页弹窗 |
| `features/index.html` + 4 个 `features/*.html` | 功能地图 / 创作项目 / 素材库 / 任务中心 / 账号中心 | 🆕 2026-11-08 新增 · 见「原项目功能原型」 |
| `canvas/_test-retouch.html` | 局部重绘交互 | 🧪 测试 · 不接业务 |
| `harness_decision.html` | harness 四方案对比 | 📌 结论页 · 已讨论完 |
| `platform_shell_v16/v17.html` | 平台外壳 | ⏸ 停 · 被画布 + Agent 页取代 |
| `canvas_*.html`（27 个） | 历史迭代 | ⛔ 别改，见下节 |

> 实测：8901 + Chrome 无头逐页跑，14 页零 JS 报错、零 404、零溢出、零小字；
> 从画布点「摄影参考库」真跳过去且当前页高亮；深/月光/晨曦三主题都验过导航可读。
> 改 `shared/` 里的 js 后按门禁把所有 `?v` 一起 bump（本轮终值 `202611072335`）。

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
> 生图那套已改成**画布对话里的弹层**（`gen-ref/` 独立页已删，不要再提），见第二节末尾。

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
| 画布（默认带 12 镜示例） | `http://127.0.0.1:8901/canvas/index.html` |
| 画布（真空态） | `http://127.0.0.1:8901/canvas/index.html?empty=1` |
| 摄影参考库 | `http://127.0.0.1:8901/photo-ref/index.html` |
| Agent 页面 | `http://127.0.0.1:8901/photo-ref/agent-page.html` |
| 3D 导演台 + 助手 | `http://127.0.0.1:8901/previs/director-agent.html` |
| 多角度（独立页） | `http://127.0.0.1:8901/canvas/multi-angle.html` |
| harness 方案对比 | `http://127.0.0.1:8901/harness_decision.html` |
| 生图参考组合 | 在画布里说「凑一组参考」→ 弹层（不是独立页） |
| 原项目功能地图 | `http://127.0.0.1:8901/features/index.html` |
| 创作项目 / 素材库 / 任务中心 / 账号中心 | `features/story-desk.html` · `features/assets.html` · `features/tasks.html` · `features/accounts.html` |

**改完必须加 `?nc=<随机>` 防缓存假阴性**（`AGENTS.md` 的规定）。
改了 `js/` 或 `css/` 还要把 `canvas/index.html` 里所有 `?v=<日期时间>` 一起 bump。

### 卡片里的图从哪来（2026-11-05）

`canvas/assets/thumbs/` 下 24 张 SVG：`story-01..12`（人物分镜）、`promo-01..06`（建筑/产品）、
`char-01..06`（角色 6 角度）。都是**本地生成的抽象摄影氛围片**（渐变 + 光 + 几何 + 剪影 + 暗角），
不是真照片、不引用外链、不涉及第三方版权。原型只要「看起来是一张片子」，不用真素材。

- 重新生成：`python docs/prototypes/canvas/tools/gen_thumbs.py`（固定 seed，可复现）
- 换题材改 `STORY` / `PROMO` / `CHAR` 三组配置即可
- 接线在 `js/02-canvas.js` 的 `demoFill()`：`thumbUrl` 按批次拼路径，渲染层已有真图分支
- 摄影参考库**没有动**：它有自己的一套卡片结构，别把这套塞进去（见第三节）

---

## 六、登记规则

- 新加原型文档 → 在本文档对应分区加一行
- 原型被推翻 → 不要删，移动到「已废弃」并写清被谁取代
- **单篇 ≤12KB**，超了拆主文件 + reference 子文件


**11-22 生成墙结果区 + 画布外壳**（用户「右边结果太小了，一个生成占一个大的，历史的小一些」、
「画布的抄下这个 https://github.com/basketikun/infinite-canvas」）：
- `features/gen-wall.html` 生图结果从 6 张等大网格改成**左边一张大图 + 右边两列小历史**
  （1440 下大图 706×397、1920 下 946×532，小历史 112px 方格）；点小卡切换大图，生成后新图
  自动当大图并挂「最新生成」角标，空态 / 详情 dialog / 复制 / 删除都保留。真实前端仍是
  Row/Col 网格，原型是为了一眼看清结果才放大，页脚口径已注明。
- `canvas/` 新增 `css/09-jimeng.css` + `js/39-jimeng-shell.js`，**只加外壳不改 01..38 的节点、
  连线、浮层逻辑**：左侧节点栏收窄到 158px（资产/节点两 Tab + 搜索）、画布空白右键弹
  「选择节点」浮层、选中节点蓝框 + 两侧圆形把手、上方浅色胶囊条
  （信息 / 删除 / 存资产 / 生图 / 缩小 / 放大）、下方紧凑输入框
  （参考内容 / gpt-5.5 / 模型·自动·1次 / ↑）、底部居中工具条、左下缩放条。
  参考项目是 MIT 的 basketikun/infinite-canvas，只借交互形态与布局节奏，没搬代码和文案。
- 底部提示会让位：`.jm-on .ghint{display:none}`、`#hintBar{bottom:72px}`，避免压住底部工具条。
- 验收：`ylcraft_verify_font13.py` OK（22 页 × 1440/1920 零小字/溢出）；画布切模式、点节点、
  右键加节点、点工具条、缩放共 7 步 0 报错；画布页 `?v` bump 到 `202611222030`（50 处）。


**11-22 晚 · 画布外壳二改（用户「参考项目配色更舒服、双击出现节点、右键拖拽画布」）**：
先按 `docs/architecture/CANVAS_TECH_CHOICE.md` + `2026-10-18_canvas_license_audit.md` 的既有结论
**不整套重构**：真实前端是基于 `basketikun/infinite-canvas`（MIT，逐字重合仅 2.6%）的派生，
自有端口校验 / WorkflowTrace 等逻辑不在上游；原型层只重构**样式与操作手感**，功能点一个不动。
- 配色从纯黑改参考图的**深灰阶**：画布 `#1b1b1b` + 24px 细线方格、左栏 / 顶栏 `#1c1c1c`、
  右键菜单 `rgba(38,38,38,.97)` 半透明 + 衬线图标、底部工具条 / 缩放条同款深灰。
  🔴 踩坑：原生 `<button>` 不带 `background:transparent;border:0` 会露出浏览器默认**白底凸起**，
  菜单项和工具条一开始全白，已逐个补齐。
- 操作按参考对齐：**双击空白**弹「选择节点」浮层（用 capture 抢在 `31-zoom.js` 的双击复位之前；
  复位入口挪到左下缩放条）；**右键按住拖拽平移**、右键轻点弹菜单、右键拖过不弹（35-infinite.js
  只管左键平移，本文件补右键那半边，不碰它）。
- 验收：1440 截图比对深灰阶 / 菜单图标 / 无白底按钮；双击与右键各 1 步弹菜单、拖拽使 scrollTop
  0→100 且菜单不弹；全站 `ylcraft_verify_font13.py` OK；`?v` 终值 `202611222200`（50 处）。


**11-22 深夜 · canvas-oss：直接跑上游无限画布 + 三主题改造**（用户「你去自己研究他有什么功能怎么改造」）：
- 新建 `docs/prototypes/canvas-oss/`，放完整 `basketikun/infinite-canvas` 源码（507 文件 / 7.3MB，
  MIT LICENSE 保留），React 19 + Vite 7 原样跑。npm 缓存与依赖都设到 F 盘不碰 C 盘。
- 三路只读研究（结论见当日工作日志）：上游 6 内置节点（图片/文本/配置/视频/音频/组）+ 插件系统
  （`registerNodeDefinitions`，复制 template 即加节点）；上游已有 17 项功能我们 16 项有原型；
  **上游没有**：镜头墙/素材墙双视图、影视分镜模型、本地像素后期 13 JS、门禁、制作实况看板。
- 对齐结论：第一阶段只做镜头节点插件 + 三主题改造；像素后期 13 JS 第二阶段单独做。
- 已改（第一阶段主题部分）：
  - `web/src/stores/use-theme-store.ts`：ThemeName 扩成 deep/moonlight/dawn（+ light/dark 旧别名兼容），
    persist version 2 + migrate 旧 dark/light。
  - `web/src/lib/canvas-theme.ts`：三套色板——deep（上游 dark 原值 #181715）、moonlight（紫 #1d1a24）、
    dawn（亮白 #ffffff）；旧 light/dark 作别名保留。
  - `web/src/components/canvas/canvas-toolbar.tsx`：外观面板从两按钮改三按钮（深海/月光/晨曦），
    CanvasThemeButton 改原生 button（AnimatedThemeToggler 只认两套）；阴影判断改暗色三档。
  - `web/src/components/layout/app-providers.tsx`：`.dark` class 改 `theme !== dawn && theme !== light`；
    `user-status-actions.tsx`：顶栏按钮映射三主题 ↔ light/dark。
- 🔴 环境坑：npm optional dependency 连漏 3 个 Windows 原生包（rollup / lightningcss / tailwind oxide）；
  lightningcss 要把 `.node` 二进制复制进 `node_modules/lightningcss/` 走 fallback；**补完包必须清
  `node_modules/.vite` + 重启 dev server**，否则页面还显示旧 PostCSS 错误。
- 验收：`npx tsc --noEmit` 仅剩上游自带 antd 类型错误（model-script-editor:58，与改造无关）；
  无头 Chrome 实测三主题按钮都在、点月光后画布从暖灰变冷紫、0 报错；截图 `oss_theme_ui.png` /
  `oss_moon_ui.png`。

**11-23 凌晨 · 镜头节点方案推翻，改做「AI 拆成分镜」**（用户连问「镜头节点和视频节点区别 / 单独存在必要性 /
即梦应该是文本节点 LLM 写剧本再拆」）：
- **结论：镜头节点插件砍掉**。上游视频节点本就能生成（`project.tsx:2540`）+ 上传（`:1508`），
  模型默认 `grok-imagine-video`；ComfyUI 的 Text Split 也只是按 `##` 机械切，不是智能拆分。
  用户定的流程才对：**文本节点 LLM 写剧本 → AI 拆成 N 个分镜文本节点 → 每镜拖出视频节点 →
  输入框写「根据这个分镜生成视频」**；上游 `buildNodeGenerationContext` 已把上游文本拼进 prompt，
  整条链原生支持。分镜不需要成为一种节点，它就是几个文本节点。
- 新增 `web/src/components/canvas/canvas-node-ai-split-dialog.tsx`：两步式——先调 LLM 出分镜
  （`requestImageQuestion`，要求返回 JSON 数组），**预览可逐条改标题/描述**，点确认才建节点
  （用户强偏好：AI 结果先给人确认再落库）。`parseAiShots` 容忍 ```json 包裹 / 前后解释 / 中英文字段名。
- 接入：文本节点浮条加「AI 拆镜」（仅当节点有内容），`project.tsx` 加 `createAiSplitNodes`
  照 `splitImageNode` 同构生成 N 个文本节点 + 自动连线到剧本节点 + 全选；中英 i18n 各加一组文案。
- 验收：`npx tsc --noEmit` 仍只剩上游那个 antd 老错；无头 Chrome 打桩模型返回 3 镜，实测
  「浮条出现 → 弹窗 → 预览 3 条可编辑 → 确认 → 节点 1→4 + 3 条连线」全通、AI 调用 1 次、0 报错；
  截图 `ais_dialog.png` / `ais_preview.png` / `ais_done.png`。**未接真实模型密钥**，打桩只验 UI 链路。
- **11-23 再去上游 landing 页**（用户「后期要嵌入我们自己的项目，开头那个开始使用页面应该…」→ 选「去掉，直接进画布」）：
  `web/src/router.tsx` 根路径 `/` 从 `<HomePage>` 改成 `<Navigate to="/canvas?mode=recent" replace />`，
  复用上游内建的 auto-open（`canvas/index.tsx:66-70`：无画布则新建，有则开最近的），删 `pages/home/index.tsx`。
  实测打开根 URL 跳到 `/canvas/<id>?mode=recent`、页面直接是画布编辑器、landing 0 处、0 报错。
  i18n 的 `home.*` 文案保留未删（无引用、无害，改动最小）。

**11-23 · 端到端真跑（本地兼容桩）**：按用户选的 A，验证「剧本 → AI 拆 3 镜 → 视频节点 → 生成」。
- 文本打 `POST {baseUrl}/responses`（OpenAI Responses API，SSE）；视频打 `POST /videos`（multipart：
  model/prompt/seconds/size/ratio/resolution_name/mode…）→ 轮询 `GET /videos/{id}` → 取 `url` 或 `/{id}/content`。
- 用 `mock_ai_server.py`（127.0.0.1:8899）替代上游，实测：AI 拆镜 1 次 `/responses` 返回 3 镜 →
  确认后节点 1→4 且连线到剧本；视频节点「生成」发出 `/videos` + 4 次轮询，0 报错。
  请求体确认：拆镜 prompt 带完整剧本与 JSON 约束；视频 multipart `prompt=根据这个分镜生成视频`、`seconds=6`、`size=720x720`。
- 🔴 兼容性结论：**YLCraft 现有 `DOUBAO_API_KEY` / `MINIMAX_API_KEY` 不能直接接**——豆包文本是
  `chat/completions`、MiniMax 视频是 `/v1/video_generation`，都不是 `/responses` + `/videos` 这套。
  要真跑需二选一：① 提供兼容渠道；② 写适配层把上游转成这套格式（也是嵌入自己项目的正解）。
- 坑：persist 的 config store **version 默认 0**（代码没写 version），注入 localStorage 时写 2 会触发
  「couldn't be migrated」并整份丢弃回默认 `api.openai.com`；必须写 `version: 0`。
  Playwright 里视频节点发送按钮只有图标、`innerText` 为空，只能用 `button[aria-label="生成"]` 命中。
- 未验：分镜节点 → 视频节点的**拖拽连线**（端口坐标自动化没命中）；但连上后上游文本会拼进 prompt
  由 `canvas-node-generation.ts:49,55` 保证（`upstreamText` 拼到 prompt 尾巴）。

**11-24 · 图片编辑入口统一（用参考项目的壳 + 我们的功能）**：用户「用它的壳改造加东西，
我不懂门禁，主要要原型设计的图片编辑/切分/多角度」。
- 触发条件先查清（否则又是假阴性）：原型**画布**模式点节点只有 7 项（信息/删除/存资产/生图/缩放/更多），
  图片编辑 8 项浮条只绑在**镜头墙/素材墙**卡片上（`02-canvas.js:176-183`，且 `status==='todo'` 不弹）；
  33 项完整清单在**双击大图**里（`06-imageops.js`）。参考项目默认画布是空的，要先上传图才有浮条。
- 改动（`canvas-oss/web/src/`）：
  - `canvas-image-toolbar-tools.tsx`：storage key `v7→v8`（老用户 localStorage 存着旧 ids，
    只改 `defaultVisible` 不生效——同 persist 版本的坑）；`angle`（多角度）改默认可见；
    新增 `fullEdit` 工具（扳手图标，默认可见）。
  - 新增 `canvas-node-full-edit-dialog.tsx`：把原型 6 组 33 项清单做成面板，按「全部/本地免费/AI」筛选
    + 搜索；主题用 `canvasThemes` 摊平成语义字段（它是嵌套 `node/toolbar/canvas` 结构，没有 `theme.text`）。
  - `canvas-node-hover-toolbar.tsx` / `project.tsx`：接 `onFullEdit` → `fullEditNodeId` → 挂 dialog。
  - i18n 中英文补 `fullEdit/fullEditTitle/fullEditSearch`。
- 验收：无头 Chrome 上传图片 → 浮条实测有「生成角度」「打开 33 项图片编辑能力」→ 点开面板
  6 组 33 个按钮、点「裁剪」有 toast、0 报错；晨曦亮色下面板白底深字可读。
  类型检查只剩上游自带 antd 老错误（model-script-editor:58，与改造无关）。
  **未接真实模型**：⚡ 项点击只给 toast，本地项也只演示入口，真实现留到迁实际项目。
- 这批 `canvas-oss/` 改动已在 commit `b2674026` 提交（未推远程）；`docs/prototypes/canvas/` 的 vanilla 原型一个字没动。

**11-24 · 提示词库并集 + 多场景共享组件**：用户「1 原型设计提示词库 2 参考项目和 YLCraft 下载的取并集
3 打通画布提示词取提示词库」（对齐口径：静态打底+留接口 / 全量字段 / 画布+生图页先接）。
- 实测两边数据差别（别再猜「同名源数据一样」）：参考项目 7 源共 1742 条（标准化 GitHub JSON，
  tags/封面 100%，中文 39~100%，内部重复 19%）；YLCraft IMI 3 源共 11386 条（本地缓存 68MB，
  `chinese_prompt/english_prompt/images/view_count`，中文 95~97%，重复 0.3%）；两边正文完全相同的仅 37 条。
- 构建脚本 `canvas-oss/scripts/build_prompt_dataset.py`：原始快照存 `canvas-oss/data/prompt-sources/`
  （该目录在 `canvas-oss/.gitignore` 里，**不进 git**，用 `--fetch` 或抓取脚本重建），
  输出 `web/public/prompt-data/{manifest.json,<sourceId>.json}`，10 源 13128 条 / 73.6MB，按源懒加载。
  **IMI 大源剥掉 raw 字段**（>3000 条时）但归一化字段全保留；`D:/Python310/python.exe` 跑，别用系统 python。
- 数据源：`prompt-source-presets.ts` 7 源→10 源、URL 指向本地 `/prompt-data/`（换后端只改这里）；
  `prompt-source-runtime.ts` normalize 保留全量字段并映射 `referenceImages→referenceImageUrls`；
  store 的 merge 会按新 presets 重建内置源，所以老 localStorage 不挡路。
- 共享组件 `components/prompts/prompt-library-dialog.tsx`：参考 YLCraft `PromptReferencePicker` 的
  数据集/模型集合/来源/标签四维筛选 + 搜索 + 无限滚动 + 详情抽屉（封面/参考图/双语正文/热度统计），
  `mode=select|copy|both` 供多场景复用。已接画布节点书本按钮、生图页、视频页；左侧提示词库 tab 读同一份数据。
- 验收：无头 Chrome（生图页）打开弹窗 → 总数 13128 → 筛「YLCraft 下载库」11386 → 搜「复古」1245 →
  点「使用此提示词」弹窗关闭且输入框填入中文正文，**0 报错**；tsc 只剩上游 antd 老错误。
  坑：antd 6 的 `Spin tip` / `Drawer width` 已弃用，分别改 `description` / `size`。

**11-24 · 端口冲突修复**：YLCraft 主前端 `frontend/vite.config.ts:18` 写死 **3000**，
参考项目 `npm run dev` 脚本也写死 `--port 3000`，两个同时启动会互相抢、后启动的顶掉前面的
（用户「访问 YLCraft 启动页面结果变成参考项目」）。修法：参考项目 `web/vite.config.ts` 加
`server: { port: 3100, strictPort: true }`（支持 `VITE_PORT` 覆盖），并把 `package.json` 的
`dev` 脚本去掉 `--port 3000`（**关键**：脚本参数会盖掉 vite 配置里的 port，只改配置无效）、
`start`（preview）改 3100。验证：3000=YLCraft、3100=参考项目，两个并存各返回 200。
以后原型地址是 **http://127.0.0.1:3100**，8901 是 vanilla 原型（python http.server）。

**11-24 · 提示词库按 YLCraft 原设计重做 + 标签排序**：用户贴 YLCraft `3000/prompt-library`
截图「我们以前是这样设计的」——对照发现上一轮只对齐了筛选维度，详情/样式还是参考项目的。
- 标签真相：不是「标签少」，是**没排序**。YLCraft 后端 `PROMPT_TAG_PRIORITY` 有 **102 个精选中文标签**
  用于筛选栏排序；我们并集数据有 9664 个标签（更多），但没排序→前几个是 `gpt-image-2/Tech/photography`
  这种英文/来源名，还带 `人 像`/` 人像` 空格重复。实测 102 个精选里我们有 97 个，缺 5 个低频。
- 构建脚本：`load_tag_priority()` 从 `backend/.../service.py` **解析真实 102 标签**（不手写、不造假），
  导出 `web/public/prompt-data/tag-priority.json`；`clean_tags()` 去空格/大小写统一/去模型名与 @ 作者标签。
  前端 `prompts.ts` 读该 JSON，`collectTags` 按「优先级 → 频次」排，停用词同 YLCraft。
- 共享组件 `prompt-library-dialog.tsx` 按 YLCraft 重做：详情**左右分栏**（图左、文字右）、
  中英提示词**各自带复制按钮**、顶部操作栏（收藏/复制/加入我的资产/使用）、**风格**标签区、
  参考图组；筛选 chip 从 antd Tag 换成 YLCraft 式圆角 chip + 「更多/收起」+ 已选筛选标签展示。
  新增 `embedded` 模式供独立页复用，`onSaveAsset/onToggleFavorite/isFavorite` 回调给多场景。
- **独立页 `/prompts` 也换了**（之前漏了）：从上游旧页（两维筛选 + 旧详情弹窗）改成内嵌共享组件。
  画布 / 生图 / 视频三处调用改 `onSelect`→`onUse`，生图/视频接 `onSaveAsset`。
- 坑：卡片封面 `<button>` 里嵌收藏 `<button>` 触发 React hydration 报错 → 外层改 `<div>`、内层按钮。
  外链封面 `ERR_CONNECTION_RESET` 是网络问题（raw.githubusercontent 时通时断），图片有 onError 兜底。
- 验收（3100）：独立页 13128 条、标签前排是韩国风/手绘感/高细节（YLCraft 顺序）、详情 2 个复制按钮 +
  收藏 + 风格区、生图页弹窗 13128 条，tsc 只剩上游 antd 老错误。

**11-24 · 提示词页按 YLCraft 页面设计 + 在线同步（commit 85616db9）**：用户「这个页面也用我们的，
脚本改成参考项目那种来源同步」，对齐口径：**原型先行**（真实 YLCraft 页面不动），后期再把参考项目拆进来。
- 页面：canvas-oss `/prompts` 换成 YLCraft 主前端 `frontend/src/pages/prompt-library` 的页面骨架：
  hero（Image Prompt References + 大标题 + 副标题 + 条数/来源已同步统计）+ 右侧命令面板（模板按钮/搜索/
  仅本地开关/重建本地索引）+ 筛选面板（模型集合/分类标签，更多收起）+ 卡片网格 + 详情抽屉。
  卡片/详情/chip 从 dialog 文件**导出复用**，独立页不再自己实现一遍。
- 同步：**参考项目的在线同步机制原型本来就有**（refreshSource/refreshAllSources/refreshDueSources/
  调度器 60s/缓存/来源开关/新增源/查看内容/立即拉取），上一轮只是 URL 指向本地种子。
  本轮补齐「在线优先、失败回落本地」：`PromptSource` 加 `onlineUrl` + `mode(local|online)`，
  `runPromptSource` 按 mode 选 URL，在线失败回落种子 JSON；7 个 OSS 源带 GitHub raw 在线地址，
  3 个 IMI 源只有本地种子；来源页每个源加「本地/在线」切换按钮（内置源也能切），编辑器加模式/
  种子地址/在线地址字段，store 的 merge 保留 mode/onlineUrl（否则刷新丢失）。
- 脚本 `build_prompt_dataset.py` 从一次性 build 变增量同步工具：`--source <id>` 只更新一个源、
  `--fetch` 从在线拉快照（urllib 需 `ProxyHandler({})` 绕过坏代理）。实测 `--source awesome-gpt-image`
  后 manifest 仍 10 源 13128 条。
- 坑：i18n 的键要放进 `config.promptSources.editor.*`，别新建同级 editorExtra；
  两次加 modeLocal 到 promptSources 造成 TS1117 重复键，删掉 runtime 后面那份。
- 验收（3100）：新页 hero/统计/重建按钮/20 卡片/0 报错；点「重建本地索引」同步成功；
  来源页 10 个本地按钮，点第一个切在线变 9 个（生效）；tsc 只剩上游 antd 老错误。

**11-24 · 补「我的生图提示词」+ youmind 真并集（10 源 13,128 → 11 源 13,309）**：用户「现在哪个提示词库是全的
合并时候怎么合并的」，并纠正叫法——**YLCraft 才是我们的项目**，canvas-oss 是参考开源项目的本地副本。
- 实测 YLCraft 后端 `/api/v1/image-prompts/sources` 9 源，并集缺两块：`ylcraft-my-image-prompts`（我的生图提示词 2 条）
  完全没进；`youmind-gpt-image-2` 注册表 126 条 vs YLCraft 247 条。查证后确认**两边内容几乎不重叠**
  （正文交集只有 1 条、标题零交集）——因为注册表快照来自英文 README，YLCraft 解析的是 `README_zh.md`，
  所以谁都不全，真并集 **305 条**；且 YLCraft 那 247 行里有 67 行内部重复。
- 做法：新增 `data/prompt-sources/ylcraft-backend/*.json` 快照（抓取脚本 `scripts/fetch_ylcraft_prompt_sources.py`
  走后端 `/references` 分页；快照目录不进 git，需后端在 8000 跑着重建），
  构建脚本加第三数据集 `YL_BACKEND_SOURCES`——`mode=merge` 把补到的条目按正文去重后折进同名源
  （youmind 126+247 行 → +179 新增、68 重复丢弃 = 305），`mode=own` 独立成源（我的生图提示词 2 条）。
- 数据集标签不再露英文 id：`DATASET_LABELS` 映射 参考项目 / YLCraft 下载库 / YLCraft 我的库 / 合并补全。
- 页面文案对齐 YLCraft 真实页：H1「生图提示词参考库」；卡片改 3 列（原来 4 列太密）。
- 修两个真 bug：独立页 `onScroll` 挂在不可滚动的网格上（**加载更多永远不触发**），移到外层滚动容器，
  实测 20 → 140 张；封面 `onError` 只把 img 隐藏、留一块灰，改成显示「无封面」占位。
- `youmind-gpt-image-2` 的 `onlineUrl` 置空：本地种子已是 305 条超集，切「在线」反而会掉到注册表的 126 条。
- 验收（3100）：13,309 条 / 11 个来源已同步、四个数据集 chip 中文、滚动加载 20→140、0 报错。

**11-24 · 页面按 YLCraft 真实版式重排 + 封面全部改远程（commit dd6920a0）**：用户「参考项目的数据结构是什么为什么
比我们少了好多标签的感觉；在原型上面改 YLCraft 的页面结构；拉取提示词包括不本地存图片用参考项目的」。
- 数据结构实测：参考项目 7 源只有扁平 `tags`（445 个不同值，**没有 category**；25% 是模型名/来源名/作者名，
  76% 非中文，12 组大小写重复：UI/ui、Poster/poster）。YLCraft 是两层：`category` 49 个中文分类 +
  `tags` 180 个风格标签 + `model_group`。所以「感觉标签少」不是数量少，是**缺分类维度 + 标签被噪声稀释**。
- 拉取方式：参考项目 = 每个源一个 JSON URL、运行时 fetch、IndexedDB 缓存、图片**只存 URL 不落盘**；
  YLCraft = 后端解析入库 + 下载媒体到 `storage/.../media`（647MB）再改写 URL。原型采用前者。
- **真 bug（本轮修掉）**：`normalise_imi` 把 `images` 当字符串数组处理，实际是 `{url,path,...}` 字典 →
  参考图全丢、封面回落成站点相对路径 `ChatGPT/14904/14904-1.jpg`（只有 YLCraft 本地缓存能访问，上游 403）。
  改成取 `images[].url` 后 **13,303/13,309 张封面变成远程地址**（img.opennana.com 实测 200）。
- 标签清洗补中文内空格：`街 拍`→`街拍`、`人 像`→`人像`（原来只把连续空格压成一个，中文标签仍匹配不上）。
- 页面按 YLCraft `prompt-library` 的实测版式重排：居中 hero（标题 `clamp(34px,4vw,56px)`、统计 pill）、
  760px 命令面板、**整行筛选条 + 96px 标签列**、卡片网格 `repeat(auto-fill,minmax(278px,1fr))`、
  封面 `aspect-[4/4.7]` + 模型角标 + 「N 张图」角标。
- **坑**：这个项目的全局 `button` 重置压过 Tailwind 的 `text-*`（`font-size`/`color` 在 button 上不生效，
  `font-weight` 却生效），chip 渲染成白底白字。解法：文字放 `<span>` 里，别再往 button 上加 `text-*`。
- **「仅本地 / 远程更新」开关原来是假的**：它只改按钮文案，`doRefresh` 根本不看。已接成真实行为——
  切开关会遍历所有源调 `setSourceMode`（有 `onlineUrl` 的切 online，没有的留 local）再 `refreshAllSources()`，
  在线失败仍回落种子。实测：切换后真的去拉 `raw.githubusercontent.com`、按钮变「更新远程源」、条数仍 13,309、0 报错。

**方向共识（11-24 晚，用户明确）**：**不做「回流到 YLCraft 本体前端」**。我们一直是拿原型（canvas-oss 壳）
把 YLCraft 的功能迁移过来，原型就是目标前端；`frontend/src/pages/prompt-library` 不用照着改。
所以后续是在原型上补功能 + 把数据层从静态种子切到 YLCraft 后端 API，而不是反向搬代码。

**11-24 晚修正**：上面这段把对象叫错了。三个东西要分清——**YLCraft 本体**（`frontend/`+`backend/`，3000）、
**参考项目**（`canvas-oss/`，3100，开源的，不是我们的）、**我们的原型**（`canvas/` + `features/`，8901）。
用户要的是**在我们自己的原型里**做功能页（原型才是迁移目标），`canvas-oss` 那边只当参照实现。

**11-24 · 提示词库落到我们自己的原型（features/prompts.html，commit bb0387b8）**：
- 页面：`features/prompts.html`，原生 JS + `shared/theme.css` 令牌，结构照 YLCraft `/prompt-library`
  （居中 hero + 760 命令面板 + 整行筛选条 96px 标签列 + 卡片网格 `minmax(232px,1fr)` + 图左文右详情）。
  筛选三维：模型集合 / 数据源（带真实条数）/ 风格标签（更多·收起）；搜索、已选条件可单独移除、加载更多、清空。
  详情里复制走剪贴板，「存素材 / 送画布」只弹 toast（原型不接后端）。
- 数据：`features/data/prompts.json`（1.95MB，**11 源各取前 150 条 = 1,310 条**，同时带真实条数 13,309 做展示），
  由 `canvas-oss/scripts/make_prompt_sample.py` 生成——页面不扛 74MB 原始数据，但数字是诚实的。
  图片全部远程 URL；挂了换「图片加载失败」占位，不留空白。
- 标签清洗再补一刀：`gpt4o / freestylefly / unknown / open-design / official` 加进停用词，
  非中文含 `/` 的仓库路径类标签（`freestylefly/awesome-gpt-image-2`）直接丢；中文斜杠标签（`3D/手办/潮玩`）保留。
- 入口：`features/index.html` 卡片 + 功能域覆盖表新增一行。
- 验收（8901）：H1 居中偏差 0px、筛选行 `96px + 1148px`、5 列 247px、48→96 张「加载更多」、
  详情双复制按钮、来源筛选后 150 条、0 JS 报错（只有个别图片 ERR_NO_BUFFER_SPACE）。

