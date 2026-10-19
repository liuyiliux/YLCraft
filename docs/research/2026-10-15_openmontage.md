# OpenMontage 调研 —— 目前最贴近 YLCraft 的参考实现（2026-10-15）

> 来源：微信公众号文章 + **GitHub 仓库 README 实抓核对**。
> 仓库：`https://github.com/calesthio/OpenMontage` · 官网：`https://openmontage.video`
> 许可：**AGPL-3.0**（已在仓库确认）⚠️
>
> **为什么单独写一份**：这是我目前找到的**最贴近 YLCraft 定位**的开源实现 ——
> Agent 驱动、视频生产全流程、Markdown 技能卡、供应商打分路由、
> 预算治理、过程可视化。**它的很多设计正好回答了我们自己的问题。**

---

## 一、它是什么（仓库原文）

> **"The first open-source, agentic video production system."**
> **"Turn your AI coding assistant into a full video production studio."**

- 2026-03-29 开源，独立开发者 `calesthio`
- 文章称 68K star / 8.8K fork（**我只核实了仓库存在与活跃度，
> star 数未在页面确认** `待核实`）
- **仓库非常活跃**：最新 commit **3 天前**，PR 编号已到 **#752**
- 371 watchers，`LICENSE` = **AGPL-3.0**（已确认）

**核心区分（README 原文）**：
> 「OpenMontage can make image-based videos, but it can also make a **real video**
> for free/open-source workflows: the agent builds a corpus from free stock footage
> and open archives, retrieves **actual motion clips**, edits them into a timeline,
> and renders a finished piece. That is **not the usual "animate a handful of stills
> and call it video" trick**.」

---

## 二、🔴 最关键的一句（直接回答"agent 设计总不在点"）

> ### 「Chat tells you what the agent **said**. Backlot shows you what the production is actually **doing**.」

**翻译**：对话告诉你 agent **说了**什么；Backlot 告诉你制作过程**实际在做**什么。

> **这就是我们 Agent 页面的病根。**
> 我们现在的 `agent/index.tsx` 只显示"agent 说了什么"
> （`返回字段：success、normalized_request、visual_plan、`），
> **完全不显示"实际在做什么/做出了什么"。**
>
> OpenMontage 把这两件事**分成两个界面**：对话负责沟通，看板负责事实。

---

## 三、架构：agent-first，没有代码编排器

**README 原文**：
> 「OpenMontage uses an **agent-first architecture**. **There is no code
> orchestrator. Your AI coding assistant IS the orchestrator.**」
> 「**Python provides tools and persistence.** All creative decisions, orchestration
> logic, review criteria, and quality standards live in
> **readable instruction files (YAML manifests + Markdown skills)** that you can
> inspect and customize.」

执行链：
```
Agent 读 pipeline manifest (YAML)  → 阶段、工具、评审标准、成功门禁
Agent 读 stage director skill (Markdown) → 每个阶段「怎么做」
Agent 调用 Python 工具             → 内置 7 维打分选供应商
（关键节点停下来等人批准）
```

### 3.1 三层知识架构（**最该抄的结构**）

| 层 | 位置 | 回答的问题 |
| --- | --- | --- |
| **Layer 1** | `tools/` + `pipeline_defs/` | **"What exists"** —— 可执行能力 + 编排 |
| **Layer 2** | `skills/` | **"How to use it"** —— 本项目的约定与质量标准 |
| **Layer 3** | `.agents/skills/` | **"How it works"** —— 外部技术知识包 |

> 「Each tool declares **which Layer 3 skills it relies on**.」
>
> **注意：它用的就是 `.agents/skills/` 目录约定 —— 和我们仓库完全一致。**

### 3.2 工作流（统一流程 + 导演技能）

**每条 pipeline 都走同一条流程**：
```
research → proposal → script → scene_plan → assets → edit → compose
```

> 「Each stage has a dedicated **director skill** — a markdown instruction file that
> teaches the agent exactly how to execute that stage. The agent reads the skill,
> uses the tools, **self-reviews**, checkpoints state, and **asks for human approval
> at creative decision points**.」

**一条给 Agent 的核心指令**：
> 「**Treat every video request as a pipeline selection problem.** Pick the right
> pipeline first, then read the manifest, then read the stage skill, then use tools.」
> 以及 —— **「Do not improvise the production workflow」**（不许自己发挥流程）

### 3.3 Web 调研是一等公民

> 「Before writing a single word of script, the agent searches YouTube, Reddit,
> Hacker News, news sites, and academic sources... then **cites everything in a
> structured research brief**. Your videos are grounded in real, current
> information, **not hallucination**.」
> —— 单次制作会跑 **15–25+ 次网络搜索**

---

## 四、生产治理（Production Governance）—— 最值得学的部分

> 「OpenMontage treats video production like real engineering — with
> **quality gates, audit trails, and enforcement** at every stage.」

### 4.1 质量门禁

| 机制 | 原文要点 |
| --- | --- |
| **人工批准是强制的** | 「Human approval gates are **enforced, not suggested**」——proposal / script / scene plan / assets / publish 全部暂停等签核；**checkpoint writer 拒绝**没有记录批准的「completed」阶段；被取代的 checkpoint 会归档，**审计链在多次修订后仍存活** |
| **Pre-compose 校验** | 若违背 delivery promise（例如声称「motion-led」却 80% 是静图）、slideshow 风险分为 critical、或缺渲染器族 → **阻止渲染**。「Catches broken plans **before wasting GPU time**」 |
| **Post-render 自审** | 每次渲染后跑 ffprobe 校验、**在 4 个位置抽帧**查黑帧与破损叠加、**分析音频电平**查静音与削波、验证 delivery promise、检查字幕是否存在。**若自审失败，视频不予展示** |
| **Slideshow 风险评分** | **6 维分析**（重复度、装饰性视觉、弱运动、镜头意图、排版依赖、无依据的电影感宣称）防止「动画版 PPT」 |
| **源素材探查** | 用户自带素材先探测（分辨率/编码/声道/时长）再规划，「**No hallucinating content from filenames**」 |

### 4.2 供应商打分选择（7 维）

> 「task fit (**30%**), output quality (**20%**), control features (**15%**),
> reliability (**15%**), cost efficiency (**10%**), latency (**5%**),
> continuity (**5%**)」

- **赢家和落选者都记日志**（含分数）
- `task_context` 归一化：把模糊需求（如"Pixar 风格、角色一致性"）展开成
  打分器能吃的意图与风格信号
- 选择结果会**带出该供应商的 agent_skills**，让 Agent 立刻去读对应的 Layer 3 技能

### 4.3 决策审计链

> 「Every major creative and technical choice — provider selection, style/playbook
> choice, music track, voice selection, renderer family, any fallback or downgrade —
> is logged with **alternatives considered, confidence scores, and reasoning**.」

### 4.4 预算治理

`Estimate`（执行前估价）→ `Reserve`（调用前锁定）→ `Reconcile`（记录实际花费）
模式：`observe`（只记录）/ `warn`（超额告警）/ `cap`（硬上限）

文章补充：**单次动作超过 0.5 美元要确认，总预算默认 10 美元封顶**，
「绝不出『惊喜账单』」`（来自文章，仓库未逐一核对）`

---

## 五、Backlot：把"过程"变成一等公民

> 「**Backlot shows you what the production is actually doing** — a local board
> that fills itself in as the pipeline runs. Stages light up, the script lands as a
> screenplay page, scene cards shimmer while assets generate, and **every provider
> decision and dollar spent is on the wall**.」

关键设计（README 原文）：

| 机制 | 原文 |
| --- | --- |
| **零配置自动打开** | 「the agent opens it for you automatically. **No setup, no reporting** — the board **derives everything from the project files the pipeline already writes**」 |
| **是批准门禁** | 「**The storyboard is now a real approval gate.**」 |
| **在渲染前批准** | 「Asset generation **pauses on a scene-by-scene contact sheet** — takes, prompts, **per-asset cost, quality scores** — so you approve the visuals **before the render**, not after it's too late」 |
| **可回放** | `▶ REPLAY RUN` —— 「the whole production replays from its timestamps, **scrubbable end to end**」 |
| 命令 | `python -m backlot open`（库视图）/ `python -m backlot open <project-id>`（单次制作） |

> 💡 **「derive everything from the project files the pipeline already writes」**
> 是个关键设计：看板**不要求流水线额外上报**，而是从既有产物推导。
> 我们用「从后端 assets/logs 独立验证」时，本质是同一个思路。

---

## 六、免费路线与成本（读者最关心的）

| 路线 | 成本 | 说明 |
| --- | --- | --- |
| **纯零 Key** | **0 元** | Piper 本地离线配音；Archive.org / NASA / Wikimedia Commons 免费真实素材；Remotion / HyperFrames 渲染；FFmpeg 剪辑 |
| 配一个图/视频 API | ~$0.15–1.50 / 条 | |
| 全家桶 | ~$1–3 / 条 | |
| 有 GPU | `make install-gpu` | 解锁 WAN、Hunyuan 等**本地**视频模型 |

**官方案例成本**：
- 《THE LAST BANANA》60 秒皮克斯风动画 —— **$1.33**
  （6 段 Kling v3 画面 via fal.ai + Google Chirp3-HD 配音 + 免版权钢琴 + 逐字字幕 + Remotion 合成）
- 《Reimagine Your Universe》50 秒竖版 —— 约 $4
- 模型展示片 —— 约 $5

**零 Key 的能力**：
- **图像驱动视频**：Piper 配音 + 图片 + Remotion 动效
- **本地角色动画**：SVG rig + 姿态库 + GSAP 时间线 + HyperFrames
- **真实素材纪录片**：从 Archive.org / NASA / Wikimedia Commons
  **建 CLIP 可检索语料库**，再剪成片（需明确说 "use real footage only"）

> 💡 **CLIP 可检索语料库** 这个做法，和我们的向量检索思路同源 —— 值得细看。

---

## 七、对 YLCraft 的意义

### 7.1 它验证了我们的方向，也暴露了我们的缺口

| OpenMontage 的做法 | 我们 | 差距 |
| --- | --- | --- |
| 对话与"实际在做什么"**分成两个界面** | 只有对话，且压成文字摘要 | **这是"不在点"的根因** |
| 每个阶段有 **Markdown 导演技能** | 有 `backend/app/skills/`（13 个） | 结构类似，但覆盖不全 |
| 三层知识架构（能力/用法/原理） | 只有一层（skills） | 缺"能力清单"与"原理知识包"的显式分层 |
| **人工批准是强制的**（含 checkpoint 拒绝） | 有确认流程，但**点了不生效** | 实测过的 bug |
| **Post-render 自审，失败则不展示** | 无 | 值得引进 |
| **决策审计链**（含备选与理由） | 有事件日志，但无"为什么选它" | 缺少决策理由 |
| **预算治理**（估价→锁定→对账） | 有 `CostMeter`（`docs/README.md` 提到） | 有基础，未见门禁 |
| **供应商 7 维打分选路** | 有 provider 选择，未见打分 | 缺 |
| **过程可回放** | 有事件时间线 | 接近，但非"制作回放" |

### 7.2 直接可用的三条

1. **把"对话"和"制作实况"分开** ——
   我们已有素材库、任务中心、事件日志，**缺的是把它们变成"制作看板"**。
2. **门禁要"强制"而非"建议"** ——
   OpenMontage 的 checkpoint writer **会拒绝**没有批准记录的完成态。
   我们的确认按钮实测点了不生效，**连"建议"都没做到**。
3. **渲染/产出后自审，失败不展示** ——
   我们有 ffprobe 能力吗？`ffmpeg` 已在用（元数据清理）。**可复用。**

### 7.3 ⚠️ 许可风险（必须先看这一条）

**OpenMontage 是 AGPL-3.0。** 这是**强传染性**许可：
- 直接复制代码进 YLCraft → **可能要求 YLCraft 整体开源**
- 文章也提醒：「商用二次开发需留意**开源传染条款**」

**因此**：
- ✅ **可以学设计思路**（思路不受版权保护）
- ❌ **不要直接抄代码**
- ⚠️ 若要集成，需单独做法务判断

---

## 八、待核实

| 项 | 状态 |
| --- | --- |
| 68K star / 8.8K fork 数字 | `待核实`（仓库页未确认） |
| 单动作 $0.5 阈值、总预算 $10 封顶 | `来自文章，仓库未逐一核对` |
| Backlot 实际观感 | `待核实`（未运行） |
| 它生成的视频实际质量 | `待核实`（未下载观看） |
| 能否把它的 pipeline 思路映射到我们的短剧/漫画链路 | `待评估` |
