# 交接：画布形态迁移（canvas-to-ylcraft）2026-11-25

> 覆盖式交接记录。接手前先读 `openspec/changes/canvas-to-ylcraft/{proposal,design,tasks}.md`。

## 一句话现状

画布「形态层」（节点卡视觉/交互，照 canvas-oss 逐像素翻译 + 原型设计思想）**Phase 1 完成**，
今日 16 commit 全在本地未推；Agent 面板（Phase 2）与分镜流（Phase 3）spec 已写、代码未动。

## 框架（谁在哪）

| 层 | 文件 | 说明 |
|---|---|---|
| 主题令牌 | `frontend/src/components/canvas/canvas-theme.ts` | deep/moonlight/dawn 三主题（翻译自 canvas-oss），选中色统一品牌青 #22d3ee |
| 皮肤 CSS | `frontend/src/components/canvas/canvas-skin.css` | .yl-cnode 卡壳（24px 圆角+2px 边）/端口点/悬浮标题/工具条/面板/占位，全 yl- 前缀 |
| 画布表面 | `frontend/src/components/canvas/InfiniteCanvasSurface.tsx` | 背景主题化、CanvasGrid 三模式、连线降噪、小地图、renderNode 加 scale |
| 节点卡 | `frontend/src/pages/canvas/index.tsx` 的 `CanvasNodeCard` | 卡内内容直出 + configPanel 选中浮层（counter-scale） |
| Composer | 同文件 `GenerationComposerCard` / `CanvasReferenceChips` | 生图配置（参考形态），渲染在 .yl-nodecfg 浮层 |

## 关键机制（改之前必读）

1. **连线端点是 DOM 实测**：Surface useLayoutEffect 量 `[data-canvas-port-direction]` 元素中心。改端口位置零几何风险，但**同一 (node,port,direction) 只能有一个锚**——变量表格里不许再渲染带该属性的 dot。
2. **`data-canvas-no-drag` 是交互白名单**：命中的 pointerdown 直接被 Surface 忽略。任何铺满卡面的展示层带它 = 点节点无反应（ef3f8a7d 踩过）。
3. **设计定版：只留一个图片节点**——image_model/image_batch 已退役（菜单/dock 无入口），生成内联进图片节点（runNode 的 image 分支：有 prompt 就 generateImageApi，结果写回本节点）。存量节点仍兼容运行；starter 模板还在建旧节点（待迁）。
4. **Agent 双运行时**：内置（本体 agent.py 30+ 端点，门禁/skill-draft/delegate 全有）+ 外置 Codex 桥（蓝本 canvas-oss canvas-agent.ts：endpoint+token、快照推送、工具回传、审批三态）。UI 骨架用 canvas-oss，行为用原型十条思想（design.md），引擎不搬。
5. **验收判据=画面**：tsc + 无头 Chrome（`D:/Python310/python.exe` + playwright channel="chrome"）截图断言。smoke 账号 smoke_vis/Smoke#12345（canvas API 无用户隔离，Root 与 smoke 共享数据）。

## 今日 commit（全本地，按序）

8830397e 壳+背景主题 → 98fce0ce 内容即卡片 → e45206f7 占位/工具条/双击创建 →
01ab7943 生图 composer+counter-scale → b51663b8 媒体选择卡 → 2591a521 连线降噪+小地图 →
ef3f8a7d 修占位层点击 → 1b1fc69d 图片 composer+工具条五钮 → 30378f98 图片节点统一生成 →
5b572b42 面板逐项对齐 → 823639e5 有图纯图直出 → 另 5 个 openspec 备注提交。

## 下一步（建议顺序）

1. 编辑弹窗族（任务 9）：蒙版/切分/多角度/裁剪/放大，蓝本 canvas-oss dialogs，接现有图片编辑 API——有图节点工具条 14 钮的缺口就在这。
2. 版本记录（任务 27）：存/回到这版/上限 12 版（原型 34-versions 形态）。
3. 连线可选中删除（参考的透明 16px 命中层）。
4. starter 模板迁到单图片节点形态。
5. Phase 2 Agent 面板（双运行时）。

## 红线（别再犯）

- canvas-oss 只读冻结：方案 B = 架构 1:1 翻译成 React18+antd5，不引 zustand/Tailwind。
- 不重写无限画布引擎；index.tsx（7100+ 行）只做挂载接线，新逻辑进新组件。
- 翻译类工作**逐像素抄参考截图**，不能只对结构就交（用户两次点名）。
- 面板贴视口边缘出屏 = 已知遗留（fixed 层方案）。
