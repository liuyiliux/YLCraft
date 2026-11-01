# 2026-11-01 原型重构阶段性交接

> 交接给 workbuddy。**只在原型层（`docs/prototypes/`）工作，没动生产代码。**
>
> **状态更新（2026-11-01 晚）**：下面两条高优先级已查清 ——
> 功能有没有丢看 [`AGENT_PAGE_FEATURE_AUDIT.md`](../prototypes/AGENT_PAGE_FEATURE_AUDIT.md)，
> 「多角度」的真身也在那份里；v5→v6 的视觉修正见
> [`AGENT_PAGE_HISTORY.md`](../prototypes/AGENT_PAGE_HISTORY.md) 第 7 节。

## 目标

把所有页面的原型做到**审美统一**，且**原有功能不丢**。

> 用户原话：「我们设计原型就是为了做一个审美统一的平台，**只要之前功能大体都在就行**，
> 之前迁移时候微调」

## 本轮做了什么（全部在 docs/，已提交 11 个 commit）

| 产出 | 位置 |
|---|---|
| Agent 页面原型 v5 | `docs/prototypes/photo-ref/agent-page.html` |
| 3D 导演台预演助手 v3 | `docs/prototypes/previs/director-agent.html` |
| 多角度弹窗（并入 Agent 页）| 同上 agent-page.html |
| Super-agent 调研 | `docs/research/SUPER_AGENT_RESEARCH.md`（6KB）+ `_MODULES.md`（7KB）|
| 原型索引（新建）| `docs/prototypes/README.md` |

## 关键决策

1. **Agent 页 = 三栏**：左对话按项目分组 / 中主对话（创作·画布两视图）/ 右上下文面板（4 个，跟着任务变）
2. **状态条只有一条**：出问题 > 卡住 > 在跑 > 已备好，按优先级显示，不堆叠
3. **多角度 = 点图片弹圆球**（球体 + 9 方位 + 3 滑块 + 相机可拖）
4. **3D 助手 = 右下角浮层**，改动进已有的「操作历史」，AI 和手动同一列表
5. **不碰生产代码**，原型只为定「长什么样」

## ⚠️ 踩过的坑（别再犯）

1. **没要真截图就凭空设计 3D 原型** → 把「位置/目标点 + 26 类运镜 + T值 + 对焦 + 景深」
   简化成「3 个角度按钮」，**用户说这等于把功能去掉了**。
   → **做任何页面原型前，先要截图。**
2. **端口 8899 被 `G:\摄影\YL摄影\site` 占用**，用 8901。
3. **三条状态条堆在一起**违反自己的规矩（一屏 ≥4 区块该折叠），已改。

## 校验结果

| 项 | 结果 |
|---|---|
| 所有原型页面 | ✅ bsk 实测，DOM 检查通过，控制台无报错 |
| 3D 光学数字 | ✅ 和真界面一致（FOV 40 / 40.0° / 2.73–3.32m / 30.39m）|
| 引擎术语泄漏 | ✅ 扫 8 个词，0 泄漏 |
| 文档体量 | ✅ 均 ≤12KB |
| 生产代码 | ✅ 一行没动 |

## 待办（下一步）

| 优先级 | 事项 | 阻塞点 |
|---|---|---|
| **高** | 补真实「AI 创作」页截图，核对功能有没有丢 | 等用户给图 |
| **高** | 多角度功能**我们现在有没有** | 等用户确认 |
| 中 | 画布页按同一套审美统一 | — |
| 中 | 摄影参考库按同一套审美统一 | — |
| 低 | `PHOTO_REFERENCE_LIBRARY_REQUIREMENTS.md`（224KB）拆 | 待拆 |

## ⚠️ 仓库里还有别人的活

`git status` 有 **33 项未提交改动**（`frontend/src/` 20 个、`backend/` 8 个等），
是另一个 AI 在做「连接器 → 模型」选择逻辑重构。

**不是我的，没动过。** 动它们之前先确认。

## 参考

- 原型索引：`docs/prototypes/README.md`
- 指导思想：`docs/research/SUPER_AGENT_RESEARCH.md`
- 门禁：`.agents/skills/ylcraft-platform-baseline`、`ylcraft-interaction-quality`
