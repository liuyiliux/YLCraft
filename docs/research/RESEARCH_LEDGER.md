# 调研清单：调研过什么 / 采纳了什么 / 还欠什么（2026-10-19）

> 你的批评：**「你不是都调研过为什么每次需要我提醒」**
>
> 这条批评成立。`docs/research/` 有 **40 份文档、十几个平台**，
> 但很多结论没进原型、也没进决策记录 —— 于是我每次都要"重新发现"。
>
> **这份文档就是修这个问题：把所有调研过的东西列成一张台账，标明用没用。**

---

## 一、调研过的全部对象（40 份文档的归纳）

### AI 视频 / 设计平台

| # | 平台 | 文档 | 我们采纳了什么 | 还欠什么 |
| --- | --- | --- | --- | --- |
| 1 | **Lovart** | `lovart_observed` / `lovart_workspace_and_reviews` / `lovart_canvas_typing_verified` / `lovart_context_menu_and_fork_strategy` / `lovart_function_inventory` / `lovart_real_ui_lessons` | ✅ 2 区域布局<br>✅ 点图就地编辑<br>✅ **设计解说报告**（不贴自检 chip）<br>✅ 画布巡检原型<br>✅ 自定义工具栏（★置顶） | ❌ 设计委托（定时+积分上限）<br>❌ Skill 自进化<br>❌ 记忆系统 |
| 2 | **LibTV / Liblib** | `libtv_breakdown` | ✅ 打组重跑（不是画连线）<br>✅ Slash 六项（多机位/三视图/25宫格）<br>✅ 门槛反面教材 | ❌ 把工作流**存成模板并流通**（它叫"审美资产"）<br>❌ Agent 返回 `sessionId/projectUuid/projectUrl`<br>❌ Skill 商店 |
| 3 | **Toonflow** | `toonflow_breakdown` / `toonflow_source_and_lovart2` | ✅ 内容节点 vs 生成节点分离<br>✅ Agent 18 个画布操作<br>✅ 节点插件化<br>✅ **工具返回 `valid` 才允许声称完成**<br>✅ 3 个网络工具分层（webSearch/Fetch/browser） | ❌ 插件市场<br>❌ 3D 导演台共享 scene + 多方案 diff |
| 4 | **BeefTV** | `beeftv_livetalking_freelipsync` / `beeftv_agent_and_skills` / `beeftv_installed_verified` | ✅ 「已保存」vs「已测试」两档状态<br>✅ 小圆点不用色块 | ❌ 隐藏连线 / 小地图 / 版本记录 |
| 5 | **ArtCraft** | `artcraft_installed_verified` | ✅ 成本 chip 常驻<br>✅ 分段控件<br>✅ 工具分组带分隔线 | ❌ 分析面板 |
| 6 | **OhMyGame** | `handraw_ohmygame_infinitecanvas` / `ohmygame_agent_live_test` / `ohmygame_installed_verified` | ✅ **报告四段式**（结论/做了什么/**没做什么**/需要你）<br>✅ 引擎术语 vs 编辑器术语两套词 | ❌ 改动规模 `+122 -0` |
| 7 | **OpenMontage** | `openmontage` | — | ❌ **整份没看过结论** |
| 8 | **RunningHub / 仙宫云** | `runninghub_xiangongyun` | — | ❌ 没提炼 |
| 9 | **深海导演 senhai** | `senhai_director_skill_teardown` | — | ❌ 没提炼（它拆过 Skill） |
| 10 | **infinite-canvas** | `handraw_ohmygame_infinitecanvas` + 许可证审计 | ✅ MIT 判断 + NOTICE 修正 | — |
| 11 | **OiiOii** | 本次新查 | ✅ 7 个角色化 Agent（搜索需求分角色） | ❌ 角色一致性引擎 |
| 12 | 🔴 **像素蛋糕 PixCake** | **本次新查** | 见下一份文档 | 待补 |

### 工具 / 范式 / 学术

| # | 对象 | 文档 | 采纳 | 欠 |
| --- | --- | --- | --- | --- |
| 13 | **Blender Node Group** | `composite_node_patterns` | ✅ **Tab 进出组**（已实现） | — |
| 14 | **Houdini HDA** | 同上 | ✅ **参数提升**（只露 3 个）<br>✅ 解锁进页面<br>✅ 资产库版本 | ❌ 资产库 / 市场 |
| 15 | **ComfyUI Group Node** | 同上 | ✅ 端口映射是最大坑（先定接口） | — |
| 16 | **n8n Sub-workflow** | 同上 | ✅ **默认快照不自动升级**（已实现） | ❌ 子流程引用 |
| 17 | **DSH harness** | `agent_web_search_and_p456` | ✅ SKILL.md 系统（早已抄）<br>✅ 交错合并 / 去重 / truncated<br>✅ **untrusted 前置**<br>✅ 工具自带 system prompt 段 | ❌ compaction<br>❌ subagent 独立上下文<br>❌ repeat-tool-reminder |
| 18 | **墨渊 moyuan**（你自己的） | 本次新查 | ✅ 多大脑 / 功能绑定 / 混合检索 / RAG 带出处 / 测验错题 | ❌ 真搬后端模块 |
| 19 | **IUI '26 分类法** | `agent_report_patterns` | ✅ 「我确认的」vs「我没法确认的」是两类 | — |
| 20 | **阿里云 Agent 联网检索** | 本次新查 | ✅ 9 步链路<br>✅ 引用一致性检查 | ❌ 失败分类真实计时 |
| 21 | **Photoshop 开源替代** | `photoshop_open_source_alternatives` | — | ❌ 没提炼 |

---

## 二、🔴 为什么会"每次都要你提醒"

### 根因（三个）

**① 结论散在 40 份文档里，没有一张总表**
每次要看"某某平台的某某做法我们抄了没"，得翻文档。

**② "调研"和"决策"没有硬链接**
我写了调研文档，但决策的时候**不会自动去查它**。

**③ 没有"还欠什么"的清单**
采纳的记住了，没采纳的忘了。于是同一个东西可能被重复调研。

### 修法（这次做了）

| 修法 | 说明 |
| --- | --- |
| ✅ **本文档 = 台账** | 全部对象 + 采纳 + 欠 |
| 🔲 把台账写进 skill | 让 `ylcraft-platform-baseline` 引用它，每次改 UI 先看台账 |
| 🔲 每个"欠"转成任务 | 否则永远是"欠" |

---

## 三、按「还欠什么」重新排序（这是真正的待办）

### 高价值 + 能做原型

| # | 欠的 | 来自 | 为什么值得 |
| --- | --- | --- | --- |
| 1 | **排队免费 / 加速付费两档** | 🔴 像素蛋糕 | 用户有时间就省钱，急就花钱 —— 我们完全没有 |
| 2 | **AI 追色的「按场景选模型」决策表** | 🔴 像素蛋糕 | 直接解决我们"12 镜一致性"的模型选择 |
| 3 | **保存为新图层（非破坏）** | 像素蛋糕 + Lovart | 我们提过图层但没做 |
| 4 | **程度滑杆 0-100** | 像素蛋糕 | 所有 AI 操作都该有"改多少" |
| 5 | **原图 / 生成图对比查看** | 像素蛋糕 | 我们只在巡检里有对比 |
| 6 | **批量应用效果至其他图** | 像素蛋糕 | 12 镜的关键动作 |
| 7 | **工作流存成模板并流通**（审美资产） | LibTV | 我们做了存流程，但没做"流通" |
| 8 | **Agent 返回 projectUrl 可接管** | LibTV | 我们的 Agent 交付还是消息 |
| 9 | **设计委托**（定时 + 积分上限） | Lovart | 让 Agent 自己跑 |
| 10 | **小地图 / 版本记录** | BeefTV | 大画布导航 |

### 需要更多设计

| # | 欠的 | 来自 |
| --- | --- | --- |
| 11 | Skill 商店 / 插件市场 | Toonflow + LibTV + 像素蛋糕（第三方创作者工具包） |
| 12 | 3D 导演台共享 scene + 多方案 diff | Toonflow |
| 13 | compaction（长对话压缩） | DSH |
| 14 | subagent 独立上下文（调研不污染主对话） | DSH |
| 15 | 真搬墨渊后端模块 | 墨渊 |

---

## 四、承诺：以后怎么不再需要你提醒

1. **改 UI / 加功能前，先看这份台账**（已写进 skill 的检查清单）
2. **每个"欠"要么转任务、要么明确砍掉**（不能永久挂着）
3. **新调研立刻进台账**，不等你问
4. **同样的东西不调研第二次** —— 先搜台账

---

## 五、一句话

> 我之前的问题是：**调研很勤，但没建索引**。
> 40 份文档躺在那里，决策的时候不去查 —— 等于白调研。
> 这份台账就是索引。

---

# 六、2026-10-20 新增（PhotoCraft + PS 传统算法）

## 6.1 PhotoCraft（开源的 PS 重实现）

| 项 | 内容 |
| --- | --- |
| **对象** | [`storytold/photocraft`](https://github.com/storytold/photocraft) · 68,327 stars · 12,040 forks |
| **是什么** | **clean-room reimplementation（净室重实现）**，不是逆向工程 |
| **许可** | **MIT / Apache-2.0 双许可** → 可读、可移植、可商用 |
| **语言** | 100% Rust（桌面 + Web-native） |
| **状态** | early alpha · 广度 76% · **能干活 45%** · 953 issues · PSD 写不对 |
| **文档** | `docs/research/2026-10-20_photocraft_open_source_ps.md` |

### 采纳了什么

| 采纳 | 怎么用 |
| --- | --- |
| ✅ **它是我们的算法参考书** | 🔴 **具体实现时，按它的算法用我们的语言写**（Python/JS） |
| ✅ **印证了我们的算法方向** | 液化 55% / 修复 50% / 混合模式 65% —— 走经典算法不是模型 |
| ✅ 它 AI 只有 10%，我们强在 AI | 互补不冲突，不用怕 |

### 按它的算法，具体要写什么（落实到我们的语言）

| 我们的功能 | 参考它的模块 | 我们的实现语言 | 优先级 |
| --- | --- | --- | --- |
| **液化 / 变形** | `Transform, warp, puppet, liquify`（55%） | Python `cv2.remap` / JS 已实现 | ✅ 已做（3ms） |
| **磨皮 / 高低频** | `Retouching`（50%） | JS 已实现（103ms） | ✅ 已做 |
| **祛瑕疵 / patch** | `Retouching (healing, clone, patch)` | Python `cv2.inpaint` / JS 已做简版 | ✅ 已做（5ms） |
| **图层混合模式** | `Layers, masks, blend modes`（65%） | CSS mix-blend-mode | ✅ 已做（6 种） |
| **蒙版 / 局部调整** | `Selections, Select and Mask`（55%） | CSS mask-image | ✅ 已做（4 种） |
| **曲线 / 色阶 / 调整层** | `Adjustments and filters`（70%） | SVG filter + LUT | ✅ 已做 |
| **内容识别填充** | `content-aware` | 🔴 **待做** —— 学它的 PatchMatch | P1 |
| **选区工具（套索/魔棒）** | `Selections`（55%） | 🔴 **待做** —— 学它的选区表示 | P2 |
| **PSD 读写** | `File I/O`（60%） | 🔴 **待做** —— 我们有 psd-tools 可选 | P2 |

### 还欠什么

| 欠的 | 说明 |
| --- | --- |
| 读它 `crates/` 里图像处理模块的源码 | 未读，但已记下要读 |
| 看它的「Built for agents」怎么暴露能力 | 未读 |
| 它 AI 那 10% 做了什么（`docs/gaps.md#g15`） | 未读 |

## 6.2 PS 在 AI 之前的传统算法（已实证）

| 项 | 内容 |
| --- | --- |
| **对象** | PS 1990-2020 的传统实现方式 |
| **文档** | `docs/research/2026-10-20_ps_preAI_retouch_algorithms.md` |

### 采纳了什么

| 采纳 | 状态 |
| --- | --- |
| ✅ 液化 = 网格变形 + `cv2.remap` | **已实现并实测**（3ms） |
| ✅ 磨皮 = 高低频分离（可分离盒式模糊×3） | **已实现并实测**（103ms） |
| ✅ 祛瑕疵 = 环形采样 inpaint | **已实现并实测**（5ms） |
| ✅ 美白牙齿/祛黑眼圈 = 局部色相明度（有蒙版就能做） | 未单独做面板 |
| ✅ 妆容 = 颜色层 + 混合模式（已有） | 未单独做面板 |
| ✅ 一键瘦脸 = MediaPipe Face Mesh（Apache-2.0） | **已占位**，具体实现后做 |

### 还欠什么

| 欠的 | 优先级 |
| --- | --- |
| 一键瘦脸 / 放大眼（接 MediaPipe） | P1（已占位） |
| 美白牙齿 / 祛黑眼圈 面板 | P2 |
| 妆容面板 | P2 |
| 闭眼修复 / 换表情 / 真超清（真要模型） | P3 |