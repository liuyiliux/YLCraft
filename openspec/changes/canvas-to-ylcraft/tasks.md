# Tasks

> 判据：**画面验收**（3000 实页 + 无头 Chrome 截图核对可见控件/文字），grep 到代码不算完成。
> 每阶段独立 commit，index.tsx 只做挂载接线。

## Phase 0: 基线

- [ ] 1. 截图基线：3000 画布页当前样子（空画布 / 有图节点 / 选中态 / 连线）存 `docs/prototypes/canvas-baseline/`，作为 Phase 1 前后对比。
  - _2026-11-25 简化：皮肤第一批已直接落地（commit 8830397e），基线以无头 Chrome 实测记录替代（背景 #181715 / 卡 #292524 / 24px 圆角 / 零报错）。_
- [ ] 2. 视觉 tokens 落点确认：定 `yl-` 前缀 CSS 文件（如 `components/canvas/node-card/node-card.css`）与 antd theme 的边界，写进本文件备注。
  - _2026-11-25 定：`components/canvas/canvas-skin.css`（卡壳）+ `canvas-theme.ts`（主题令牌，inline 注入 CSS 变量）；antd ConfigProvider 边界留 Phase 1 内部排版批次再定。_

## Phase 1: canvas-node-card 视觉层 + 编辑弹窗族

- [ ] 3. 类型对齐：`types.ts` 补 Video/Audio/Group 节点类型与插件开放类型（照 canvas-oss `types/canvas.ts`）。
- [ ] 4. 节点卡视觉组件：12px 圆角、细边、深阴影；图片卡「有图态」高度走共享常量（卡片渲染与端口/连线几何同一来源）。
  - _2026-11-25 第一批落地（commit 8830397e）：卡壳翻译自 canvas-oss（**24px** 大圆角 + 2px 边，非 12px——以参考项目为准，原 12px 口径作废）；选中青细环；`canvas-theme.ts` 三主题 + `canvas-skin.css`；有图节点常态透明直出。待续：内部排版/字号统一。_
  - _2026-11-25 第二批落地（commit 98fce0ce）：卡内「内容即卡片」——端口边缘化（CanvasEdgePortsRail，表格行/overlay 端口移除防双 anchor）、变量表格/契约/输出移入选中时卡下 `.yl-nodecfg` 面板（功能不丢）、文本卡无边框直出、标题改卡上悬浮 `.yl-nodetitle`。待续：GenerationComposerCard 内部翻译、面板 counter-scale。_
  - _2026-11-25 第四批落地（commit 01ab7943）：GenerationComposerCard 翻译为参考 Config 卡形态（标题小字/无边框输入/单行控制条/圆形运行钮，旧英文标签行清零）；面板 counter-scale（scale 1/k + max-height 内滚）。剩余遗留：MediaPickerCard 内部未翻译、面板贴视口右缘会出屏。_
  - _2026-11-25 第五批落地（commit b51663b8）：MediaPickerCard 翻译完成（标题小字/单行选择控制/预览+操作同排）——**Phase 1 全部节点类型的参考形态翻译完成**；遗留仅「面板贴视口右缘出屏」（需 fixed 层，参考项目同样存在）。_
  - _🔴 2026-11-25 用户实测 bug（commit ef3f8a7d）：空图占位层误用 `data-canvas-no-drag` 吃掉整卡点击——**教训：`data-canvas-no-drag` 是画布交互白名单，任何铺面的展示层都不能带**。同轮清理了 smoke 误建的反向连线（反向贝塞尔控制点交叉成环，参考项目同公式同样如此）。_
- [ ] 5. 选中态：青色细环，无 glow；多选框选样式同步。
- [ ] 6. 连线降噪：基线低不透明度、悬停/选中增强；端口圆点样式对齐参考项目。
  - _2026-11-25 落地（commit 2591a521）：基线 .10/1.2px、选中相关青 1.6px、箭头 marker 移除；端口边缘点已在第二批落地。_
- [ ] 7. 节点工具条（深色玻璃胶囊）：参数 / 存为素材 / 生成 / 删除 / 关闭五动作，接现有 API。
  - _2026-11-25 部分落地（第三批 e45206f7）：选中胶囊工具条（打开/删除）已上；「参数/存为素材/生成」在配置面板与图上按钮，五动作形态待整合。_
  - _2026-11-25 第七批落地（commit 1b1fc69d）：五钮齐（参数/存素材/生成青钮/删除/关闭，翻译原型 restyleWb）；存素材对图片节点真实现（proxy 转 dataURL 入库）；同批图片节点面板换 composer（参考内容 chips + prompt + 单行控制 + 圆钮），生图/逐图生图 composer 挪进浮层、卡内轻状态。_
  - _2026-11-25 第八批落地（commit 30378f98）：**设计定版「只留一个图片节点」**——runNode 新增 image 就地生成分支（有 prompt 调 generateImageApi，结果写回本节点）；面板补「+」上传钮与模型/尺寸行；菜单与 dock 移除生图/逐图生图入口（存量节点渲染与运行保留兼容，starter 模板待迁）。_
- [ ] 8. 角标：尺寸/时长比例字体、无 max-width，1080×1920 不截断。
- [ ] 9. 编辑弹窗族：蒙版编辑 / 切分 / 多角度 / 裁剪 / 放大（蓝本 canvas-oss dialogs，形态以原型定版为准），接现有生图/图片编辑 API。
- [ ] 10. 对比查看：节点「对比」→ 拖动分割 / 并排两形态。
- [ ] 11. 键盘交互：选中节点 Delete/Backspace 删除（带确认或可撤销，防误删）。
  - _2026-11-25 验证：本体已有 Delete/Backspace 删除（input/textarea 聚焦时跳过）；第三批补浮动工具条删除按钮（e45206f7）+ 双击空白创建菜单 + 空图卡占位翻译。_
- [ ] 12. 画面验收 Phase 1：与基线截图逐项对比。

## Phase 2: canvas-agent-panel（双运行时）

- [ ] 13. AgentRuntime 抽象 + 360px 面板骨架：对话/技能/历史/日志四 tab，可收起；消息带来源标识。
- [ ] 14. 内置运行时实现：接本体 `/api/v1/agent/*`（chat/runs/run tree/事件）；过程痕迹默认折叠。
- [ ] 15. 门禁审批卡：pending 步骤 → 审批卡，确认走 `steps/{id}/confirm`；拒绝给明确回执 + 「因此省下 ⚡N」；等待时输入框可用。
- [ ] 16. 画布引用：选中节点/连线摘要作为 canvasReferences 注入 `/chat`，面板渲染引用预览卡。
- [ ] 17. 技能 tab：列技能（内置技能运行时）+「从对话/从画布生成技能草稿」走 skill-candidate/skill-draft 待审批流，确认后才落库。
- [ ] 18. 委托：delegate 端点接入，触发时间 + 成本上限输入，超上限提示与可撤销（原型 38-delegate 形态，对话触发入口）。
- [ ] 19. 外置桥：本地代理连接（endpoint+token、连接/断开/超时状态）；画布快照推送、工具结果回传、审批三态（accept/acceptForSession/decline）、interrupt、外置技能列表；后端新增独立代理路由组，默认关闭。
- [ ] 20. CanvasAgentOps：画布快照序列化 + 应用 Agent 画布修改的统一层（内置/外置共用），写操作一律过审批。
- [ ] 21. 原型思想落地（对照 design 十条）：历史按项目分组 + 状态点/汇总；后台任务条 + 输入框不阻塞；Watchdog 卡住提示条；交付即接管画布卡（打开画布 ↗）；知识引用 [n] 出处 + 来源分色 + No source 区分；节点级对话框与全局栏联通。
- [ ] 22. 画面验收 Phase 2：内置对话/审批/技能草稿确认流 + 外置连接/快照/审批 + 十条思想逐条截图取证。

## Phase 3: canvas-storyboard-flow

- [ ] 23. 后端分镜拆分端点：分镜文本 → 镜头数组（LLM），独立路由 + 失败明确报错不静默。
- [ ] 24. 前端「拆分分镜」入口：文本节点 → 调端点 → 生成镜头卡 3 列网格 + 分镜表节点。
- [ ] 25. 镜头卡角标与景别标签（序号/时长/分辨率/中景·特写·远景·全景）。
- [ ] 26. 整组重跑 + 镜头统计（时长汇总行）挂顶栏工具带。
- [ ] 27. 版本记录：存/回到这版/删，自动存触发点与上限 12 版（原型 34-versions 形态）。
- [ ] 28. 小地图：类型色块 + 视口框，点/拖导航，跟缩放/滚动联动（原型 33-gmap 形态）。
  - _2026-11-25 提前落地（commit 2591a521）：本体 CanvasMinimap 开启（原被 showMinimap=false 关闭）；类型色块体系 + 青视口框 + 点击跳转已有。待补：拖拽移动视口。_
- [ ] 29. 画面验收 Phase 3：拆分→网格→重跑→统计→版本→小地图全链路截图。

## Phase 4: 收口

- [ ] 30. 全量回归：画布既有功能（文档保存/生图/素材/图片编辑桥/starter 模板）不被破坏。
- [ ] 31. 原型 README 收口注记：`docs/prototypes/README.md` 写明形态已迁本体，原型转为归档参考。
- [ ] 32. BACKLOG 同步：`docs/research/BACKLOG.md` 记录本 change 落地 commit。
