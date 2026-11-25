# Proposal: 画布形态迁移到本体（canvas-to-ylcraft）

## What

把原型（`docs/prototypes/canvas/`，8901）与参考项目（`docs/prototypes/canvas-oss/`，3100）**证明过的画布形态**落到 YLCraft 本体（3000，React 18 + TS + antd 5）：

1. **节点卡视觉与交互**（canvas-node-card）：卡片圆角/细边/深阴影、选中细环、连线降噪、节点工具条、对比查看、键盘删除等，对齐原型已定版形态。
2. **画布内 Agent 面板**（canvas-agent-panel）：360px 侧板、对话/技能/历史/日志四 tab、**双运行时**（内置 Agent + 外置本地智能体 Codex 桥）、画布引用、审批卡、技能草稿（先确认再落库）。
3. **分镜流形态**（canvas-storyboard-flow）：分镜文本 LLM 拆分 → 镜头卡网格 → 整组重跑/镜头统计/版本记录/小地图。

落点：`frontend/src/pages/canvas/index.tsx`（现有 7087 行，已接生图/素材/文档保存/图片编辑桥）与 `frontend/src/components/canvas/`。**给现有画布补形态层，不是从零建画布。**

## Why

- 原型已定版（BACKLOG 第五节 2026-11-08 收口：10 条全销账），判据是画面；但原型是原生 JS，代码迁不过去，迁的是**设计与交互形态**。
- 本体画布功能在、形态粗糙：与参考项目对比，节点卡、浮条、Agent 配置卡的观感差距明显（2026-11-25 用户对比截图确认）。
- 正式 spec 缺口：`asset-canvas-loop` 只覆盖项目关系图，`agent-workbench-ui` 只覆盖 `/agent` 独立页；即梦式分镜画布的形态层在 spec 里是空的。
- **开源愿景（2026-11-25 用户定）**：项目开源后要「人和智能体都能用」——普通用户用**内置 Agent**，开源用户的本地编码智能体（Codex CLI 等）通过**外置桥接**接管/操作画布。参考项目的外置模式（本地代理 + 画布快照 + 工具回传 + 审批）正是为此而生，两个运行时都要。

## 定位红线（反复确认过，写死）

- **开源自用**：不做付费档位；门禁批准 / 成本上限是真实 API 保护，保留。
- **不重写无限画布引擎**：只改视觉与交互层。
- **canvas-oss 只读冻结**：采用**方案 B——架构 1:1 迁移**：组件拆分、store 组织、交互逻辑、弹窗族全部照 canvas-oss 抄，Tailwind/radix/antd6 翻译成本体语言（React 18 + antd 5 + 自有 CSS），**不引入 zustand / Tailwind 新依赖**。
- **原型不是实现事实**：不接后端、不迁实现；本 change 才是产品落地点。蒙版/切分/多角度等编辑弹窗：**形态以原型定版为准，实现弹窗以 canvas-oss 为蓝本**。

## What changes

| 层 | 内容 | 涉及文件 |
|---|---|---|
| Frontend | 节点卡视觉（圆角/边/阴影/选中环/角标/工具条） | `components/canvas/InfiniteCanvasSurface.tsx`、新增 `components/canvas/node-card/` |
| Frontend | 节点尺寸单一来源（端口/连线端点跟随节点实际高度） | `components/canvas/types.ts` + surface |
| Frontend | 节点编辑弹窗族：蒙版编辑 / 切分 / 多角度 / 裁剪 / 放大（照 canvas-oss 弹窗族，形态以原型定版为准） | 新增 `components/canvas/dialogs/` |
| Frontend | 画布内 Agent 面板：**双运行时**（内置 + 外置 Codex 桥）、对话/技能/历史/日志 tabs、画布引用、审批卡 | 新增 `components/canvas/agent-panel/` |
| Frontend | 外置 Agent 桥：本地代理连接（endpoint+token）、画布快照推送、工具结果回传、审批三态、打断 | 新增 `components/canvas/agent-bridge/`（蓝本：canvas-oss `canvas-agent.ts` / `local-proxy.ts` / `use-agent-store.ts`） |
| Frontend | 分镜流（LLM 拆分、镜头卡网格、整组重跑、统计、版本、小地图） | `pages/canvas/index.tsx` 增量 + 新组件 |
| Backend | 复用现有 API（生图 / 提示词库 / **内置 Agent 运行时 30+ 端点**：chat/runs/steps confirm/skill-candidate+skill-draft/delegate）；分镜拆分新增一个 LLM 拆分端点；**外置 Agent 本地代理服务**（snapshot/工具回传/审批路由） | `app/api/v1/`（增量） |

## Out of scope

- 无限画布引擎重写（沿用 `InfiniteCanvasSurface` 的平移/缩放/连线机制）。
- canvas-oss 任何代码回流。
- 付费/排队/加速档位叙事。
- `pages/canvas/index.tsx` 的大规模重构拆分——只做增量，避免 8s2b 类风险。

## 验收判据

沿用原型规矩：**判据只能是画面**。每个 Phase 用 3000 实际页面 + 无头 Chrome 截图核对可见控件/文字，grep 到代码不算完成。
