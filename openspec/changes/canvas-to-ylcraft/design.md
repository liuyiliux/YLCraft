# Design: canvas-to-ylcraft

## 现状与落点（已核实）

- `frontend/src/pages/canvas/index.tsx`（7087 行）：画布页主逻辑——文档列表/保存、节点创建菜单、starter 模板、生图任务轮询、素材库联动、图片编辑桥（`bridge.ts`）。
- `frontend/src/components/canvas/InfiniteCanvasSurface.tsx`（1010 行）：平移/缩放/框选/连线拖拽表面。
- `components/canvas/types.ts`：`CanvasNode / CanvasPort / CanvasConnection / CanvasNodeType / CanvasViewport`。
- 本体内置 Agent 运行时（`backend/app/api/v1/agent.py`，30+ 端点）：`/chat`、sessions/threads、runs 全生命周期、`steps/{id}/confirm` 门禁、`skill-candidate` + `skill-draft`（待审批草稿）、`delegate`、run tree / linked-logs。

**策略（方案 B，2026-11-25 用户确认）：架构 1:1 迁移，语言换成本体的。** 组件拆分、状态组织、交互逻辑、弹窗族照 canvas-oss 抄；Tailwind class 翻译成本体 CSS、radix/antd6 组件换 antd 5；**不引入 zustand / Tailwind**（状态用 useReducer/context 或局部 store）。新视觉与新面板放独立组件目录，index.tsx 只做挂载与接线。

## 迁移蓝图：canvas-oss 七块 → 本体落点

| canvas-oss | 本体落点 | 备注 |
|---|---|---|
| `types/canvas.ts`（节点枚举 Image/Text/Config/Video/Audio/Group + 插件开放类型） | `components/canvas/types.ts` 对齐补齐 | 本体缺 Video/Audio/Group |
| zustand canvas stores | `components/canvas/state/`（useReducer + context） | 不引 zustand |
| `infinite-canvas.tsx` + `canvas-node.tsx` + `canvas-connections.tsx` | 沿用 `InfiniteCanvasSurface.tsx`，视觉层重做 | 引擎不重写 |
| `nodes/builtin-nodes.tsx` + 弹窗族（mask-edit / split / angle / crop / upscale / full-edit / ai-split） | `components/canvas/dialogs/` | 形态以原型定版为准，实现照弹窗族抄 |
| hover 工具条 + 各类型 settings-popover + generation 编排 | `components/canvas/node-tools/` | 对齐现有生图 API |
| minimap / toolbar / top-bar / zoom / selection / context-menu | `components/canvas/chrome/` | 版本记录/小地图挂这 |
| `components/agent/` + `use-agent-store` | `components/canvas/agent-panel/` + `agent-bridge/` | 双运行时，见下 |

## 视觉系统（设计思想先于参数——2026-11-25 从原型提炼）

以原型 `shared/theme.css` + `canvas/css/01-base.css` + `10-polish.css` 为唯一蓝本。**迁移的是整套令牌体系与设计思想，不是逐条抄 CSS**。转成本体 CSS（`yl-` 前缀，防全局污染）：

**设计思想（六条，写死）：**

1. **令牌单一事实来源**：本体侧落成 `canvas-theme.css` 一份令牌文件（对齐原型 theme.css 的规矩）：Inter + JetBrains Mono（角标数字）；**字号下限 13px**，「层级靠字重和颜色，不靠偷偷缩字」；暗色基底 `#08080a`，品牌青 `#22d3ee`。与 antd theme token 打通（色板/圆角/字体映射进 ConfigProvider）。
2. **色彩 = 阶梯 + 半透明交互色**：4 层背景阶梯、3 级边线（白 .065/.11/.18）、3 级文字；语义色与品牌青都带 soft/line 变体——交互态一律「主色 + 半透明底」，禁实心色块。
3. **形状语言**：圆角 4 档（5/8/12/16）+ 胶囊 999px；深阴影（浮层）与近阴影（卡片）两档；缓动统一 `cubic-bezier(.16,1,.3,1)` .16–.26s。
4. **浮层 = 深色玻璃**：blur(20px) + 半透明底 + 细边 + 深阴影；节点卡底暖黑 `#1b1917`（非冷灰）；选中 = 青 1.5px 细环 + 大范围极淡 halo，拒绝蓝色粗框。
5. **布局纪律**：顶栏 52px 低密度（低频工具收 ⋯ 菜单，1440 防挤爆）；菜单项不逐项描边；icon-only 按钮进菜单必须带文字；角标 = 半透明胶囊 + `tabular-nums`。
6. **形态原则（用户纠偏史，别再犯）**：连线平滑贝塞尔、端口水平出入（正交折线被否过）；角标禁「等宽字体 + max-width」；「有图态」节点高度与几何计算共用常量；验收判据 = 画面（零小字/零溢出/零 404）。

**结构落法（沿用原型踩坑修正，写死）：**

- **节点尺寸单一来源**：端口/连线端点一律从节点存储尺寸派生；「有图态」高度为共享常量，卡片渲染与几何计算引用同一常量，禁止两处手写。
- **角标防截断**：比例字体 + `tabular-nums` + 无 max-width（原型踩坑：等宽 + max-width 把 1080×1920 截成省略号）。

## Agent：双运行时（开源「人和智能体都能用」）

### 原型 Agent 设计思想（2026-11-25 从 8901 提炼，10 条——行为与信息设计以此为准）

> 来源：`AGENT_PAGE_HISTORY_V1_V4.md`（Super-agent 六原则）+ `07-agent.js` / `36-nodeworkbench.js` / `28-gate.js` / `38-delegate.js` 注释账。canvas-oss 提供**骨架与外置桥**，这 10 条提供**交互哲学**，两者正交：

1. **对话按项目分组，不暴露 Session**：左栏按「我在做哪个项目」找对话；● 在跑 / ○ 空闲状态点；底部汇总「你在 N 个对话里有 M 个任务在跑」。
2. **全双工**：后台任务条常驻对话底部（「⚙ 后台 2 个任务在跑 · 你可以继续说，不用等」），输入框 placeholder「继续说… 后台任务跑着也能发」——前台对话与后台执行解耦。
3. **分层可见**：对话项显示「后台 N 个任务在跑」，Router/Worker 分层让用户看出谁在干活。
4. **视图切换不是跳页**：创作视图/画布视图是**同一对话的两个视图**（「去画布编辑」式跳页被否过）；切视图不丢左栏对话、不丢输入框。
5. **Watchdog 主动报**：「⚠ 图片生成已经 4 分钟没新进展，看起来卡住了 [让它去查][先不管]」——Agent 主动告诉你，不是用户翻日志。
6. **投机执行**：「你还在挑图的时候，Agent 已经先把两个改写方案备好了 [用方案一][用方案二]」（依赖运行时支持，后端具备才显示）。
7. **两级 Agent**：节点级（选中节点：工具条浮上方 + 对话框浮下方，节点本体留中间）+ 全局级（右侧 420px 智能体栏，默认收起成竖条）；节点级对话留一份到全局栏，展开能接着看。
8. **交付即接管**：Agent 交付画布是「可接管的卡片」不是消息——「打开画布 ↗」直接进连线图、右栏自动收起、顶栏变「已打开」（用户纠偏：不是复制地址自己粘）。
9. **对话触发一切**：「Agent 交付与委托都由对话触发，不另造一套入口」——说「凑一组参考」就地给参考组合，说「委托它自己跑」就地出委托卡。
10. **知识引用诚实**：回答带编号出处 [1][2] 可点看原文、来源类型分色（公众号/git/网页/笔记）、**「No source」必须分开说**（模型自己想的 vs 材料里有的）、context chips 展示这次用了哪几条。

**门禁与委托补充（28-gate / 38-delegate）**：门禁真的拦人（不批准不许过），阈值触发；拒绝要有明确说明，不静默失败；被拒展示「因此省下 ⚡N」；批准记录落库带用户与时间。委托 = 排程规则（定时 × 任务 × 成本上限，超上限会停），与任务中心的单次生成是两回事。

### 双运行时架构

产品愿景：内置 Agent 给普通用户；开源用户的本地编码智能体（Codex CLI 等）通过外置桥接管画布。**同一面板，两个 Provider：**

```
AgentPanel（panel + tabs：对话/技能/历史/日志 + 来源标识）
   ├─ AgentRuntime 接口：send(msg, canvasContext) / events / interrupt / approve(step, decision) / skills / history
   ├─ 内置实现（默认，永远在线）→ 本体 /api/v1/agent/*
   │     门禁=steps/{id}/confirm；技能草稿=skill-candidate+skill-draft（待审批）；委托=delegate
   └─ 外置实现（Codex 桥，可连接/断开）→ 本地代理服务（endpoint + token）
         蓝本：canvas-oss canvas-agent.ts / local-proxy.ts / use-agent-store.ts
         协议：postState(画布快照) / postToolResult(工具回传) / approval(accept|acceptForSession|decline)
               / interrupt / skills CRUD + skills/draft(source: "conversation"|"canvas") / local-file reveal
```

- **画布操作面（CanvasAgentOps）**：把画布序列化为快照（CanvasAgentSnapshot），两种 Agent 都经同一 ops 层读画布、提修改——内置走工具调用，外置走工具结果回传。**Agent 对画布的写操作一律过审批卡**（内置三态对齐门禁 confirm；外置 accept/acceptForSession/decline）。
- **画布引用**：消息可携带 canvasReferences（选中节点/连线摘要），注入 `/chat` 上下文；面板渲染引用预览卡（蓝本 `agent-canvas-reference-preview`）。
- **技能草稿**：来源 conversation | canvas，草稿一律**预览给人确认后才落库**（本体已有待审批机制，前端只做确认 UI）。
- **明确不搬**：canvas-oss 的 `agent-event-formatters`（CLI 事件转译按内置事件模型重写）、`message-assets` 资产通道（本体走素材库）。
- 外置代理服务在 backend 新增独立路由组（snapshot / tool-result / approval / skills），token 鉴权，**默认关闭**，设置里显式开启。

## 分镜流

- 后端 LLM 拆分端点（分镜文本 → 镜头数组），不在前端硬编码规则拆分。
- 镜头卡 3 列网格 + 角标（序号/时长/分辨率/景别）；整组重跑（锁定镜头跳过）、镜头统计、版本记录（上限 12 版）、小地图——挂 `chrome/`。

## 风险

| 风险 | 对策 |
|---|---|
| index.tsx 7087 行，改动碰撞 | 新逻辑进新组件；index.tsx 只加挂载点与回调；每 Phase 独立 commit |
| antd 5 与画布 CSS 互相污染 | 全部 `yl-` 前缀类名，不写全局标签选择器 |
| 外置 Agent 越权操作画布 | 审批卡强制 + token 鉴权 + 默认关闭；快照只含可见画布内容 |
| 双运行时 UI 状态混乱 | 消息/审批卡带来源标识（内置/Codex）；连接状态显式展示 |
| 分镜端点误伤现有生图 | 独立路由文件 + 独立模型字段，`init_db()` 增量建表 |
| React 19 组件降 18 | 迁移时逐个核对 API（useSyncExternalStore 等均兼容；antd6→5 组件替换） |
