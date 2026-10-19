# AI 视频 / 短剧漫剧平台交互对比表

> 建立：2026-10-14
> 用途：给 YLCraft 界面重设计提供**可横向对比**的依据，不用形容词。
> 规则：**每格要么有来源，要么标 `待核实`**。凭印象填的标 `[推测]`。

## 为什么用这些维度

不列"好不好看"（主观、没法比），只列**能数出来的**：

| 维度 | 为什么它比"丑不丑"有用 |
| --- | --- |
| 首次出片步骤数 | 可数。步骤越多，交互越差，与审美无关 |
| 必填项数量 | 可数。必填项是"用户必须懂"的税 |
| 一致性怎么维持 | 决定用户要不要手动重复劳动 |
| 过程是否可见 | 决定用户是"在等"还是"在慌" |
| 失败后怎么恢复 | 决定一次失败是丢 5 秒还是 5 分钟 |
| 结果怎么呈现 | **YLCraft 已确认的伤**：对话里只显示文字摘要 |
| 有无产品内引导 | 有教程=流程不够自解释 |

图例：`✅` 一手实抓/读代码 · `▢` 待核实 · `[推测]`

---

## 一、总表

| 平台 | 类型 | 首次出片步骤 | 必填项 | 一致性维持 | 过程可见 | 失败恢复 | 结果呈现 | 产品内引导 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **YLCraft（我们）** | 创作全链路 | **失败：卡在确认，未出图** `✅实测` | 1（只需 prompt）`✅实测` | **角色库/资产中枢已具备，但不自动注入** `✅代码` | 有内联轨迹，但**预览信息被丢成字段名** `✅实测` | 步骤级失败建议 `✅代码`；**但错误直接甩 SQL** `✅实测` | **❌断裂：只显示文字摘要+JSON，无图** `✅实测` | **❌无** `✅代码` |
| **Google Flow** | 大厂生视频 | ▢ | ▢ | Ingredients（参考图）`✅` | ▢ | **改版后大面积失效** `✅` | 素材库「library barely works」`✅` | ▢ |
| **LTX Studio** | 故事→视频 | **4 步**：建项目→生图→动画→进 Storyboard `✅` | 低（生图只需 prompt）`✅` | **Elements：锁定角色/环境/物件，跨全部生成复用** `✅` | Gen Space 多模型对比 + prompt 历史 `✅` | **Retake：只改光线/构图/表情，不重生成整镜** `✅` | 生成即自动存入 Project，画布内预览 `✅` | 官方 4 步教程 `✅` |
| **Runway** | 节点式工作流 | 多：加 4 节点 + 连 3 条线 `✅` | 中（节点参数）`✅` | 靠参考图节点 `▢` | 节点全可见 `✅` | 单节点可单独 Run；**Node Execution History 可回滚任一历史输出** `✅` | 节点内预览 + 灯箱全屏 `✅` | 官方 Workflows 教程 `✅` |
| **Showrunner** | AI 短剧 | **极低**：Discord 里打 `/scene` 填表 `✅` | 低（角色1/角色2/场景/对话）`✅` | 上传照片+声音样本+背景故事建角色 `✅` | 在 Discord 里与他人创作流共生 `✅` | **改一句台词→重新生成，新台词融入原片（局部重生成）** `✅` | 直接出成片；脚本编辑器可改镜头类型/情绪 `✅` | 无独立教程，Discord 内直接可玩 `✅` |
| **Dashtoon** | AI 漫剧 | 低：Story Mode 输入故事即可 `✅` | 低（输入故事）`✅` | **AI 自动识别故事里的人物→映射到角色库** `✅` | 逐格剧本自动生成 `✅` | Inpainting 局部重绘（可保留原构图）`✅` | 无限画布编辑器，左侧工具栏 `✅` | 发布说明即文档 `✅` |
| **ComfyUI** | 开源工作流 | 多（用户原话："我花大量时间安装"）`✅` | 高（手动接 Text Encoder/VAE/Diffusion）`✅` | 用户自己搭节点 `✅` | 节点全可见 `✅` | 用户自己排查 `[推测]` | 画布内预览 `[推测]` | 无官方引导，社区靠 cheat sheet `✅` |
| **Liblib/Tusī** | 生图社区 | `▢` | `▢` | 参考图/LoRA `▢` | `▢` | `▢` | 画廊式 `[推测]` | `▢` |
| **oiioii** | 多 Agent 动画 | `▢` | `▢` | `▢` | **主打卖点：7 个 agent 过程可见** `▢` | `▢` | `▢` | `▢` |
| **即梦/可灵/海螺** | 大厂生视频 | `▢` | `▢` | `▢` | `▢` | `▢` | `▢` | `▢` |

---

## 一之补：YLCraft 实机实测记录（2026-10-14 17:1x）

> 方法：用浏览器登录本机 `http://localhost:3000`，在 `/agent` 对话页**实际发送**
> 「生成一张一只橘猫坐在窗台上的图片」，走完确认流程。
> **这是实测，不是读代码。**

### 实测流程逐步记录

| 步骤 | 界面实际显示 | 判断 |
| --- | --- | --- |
| 1 | 输入框：`告诉智能体要做什么。Enter 发送…` | ✅ 入口清楚 |
| 2 | Agent 调 `preview_image_generation_request` | ✅ 工具被正确触发 |
| 3 | **工具结果显示：`返回字段：success、normalized_request、visual_plan、`** | ❌ **这就是"不在点"** |
| 4 | 吐出一句：`已准备调用 generate_image_asset。这是写入、删除或消耗类操作，请确认后我再执行。` | ✅ 文案说人话 |
| 5 | 待确认卡片：`工具 generate_image_asset 等待确认：costly` / `将执行的操作` / `prompt 一只橘猫安静地坐在窗台上…` / `size 1024x1024` / `n 1` | ✅ **卡片做得不错，prompt 可读** |
| 6 | 点「确认执行」 | ❌ **没反应：状态仍是 `waiting_confirmation`** |

### 实测确认的 4 个问题

**问题 1：生图预览把"视觉信息"丢掉了（最严重）**
Agent 已经生成了 `visual_plan`（本该是"将要生成什么"的可视化描述），
但前端 `summarizeToolResult` 只显示字段名列表。
用户站在确认卡片前，**看不到任何图像预览**，只能读一段 prompt 文字。

**问题 2：点「确认执行」后没有真正执行**
实测点确认后，Run 状态仍停在 `waiting_confirmation`，8 步 / 2 工具不变。
独立验证：后端 `/api/v1/assets` 最新记录是 **2026-10-02** 的 bilibili 视频，
`/api/v1/logs` 也没有新的生图事件 —— **图片确实没生成**。
> ⚠️ 保留不确定性：我只点了两次，不排除是我点错按钮（页面上同时存在两个
> 「确认执行」：顶部待确认横幅一个、执行轨迹里一个）。**但"两个同名按钮"
> 本身就是问题。**

**问题 3：待确认横幅疑似"串台"**
我 10/14 发起的是 `generate_image_asset`，但顶部横幅上那条「确认执行」
点下去执行的是**旧对话（09/13）的 `add_asset_tag`**，报错后整个对话里
多出一条失败记录。当前对话的待确认项却还挂着。

**问题 4：原始 SQL 报错直接甩给用户**
旧对话那条失败，用户看到的是：
> `结果摘要：{"error": "(builtins.ValueError) badly formed hexadecimal UUID string\n[SQL: SELECT asset_nodes.id AS asset_nodes_id, asset_nodes.name AS asset_nodes_name...`

对照 LINUX DO 那条「参数不生效」和 ComfyUI 的教训：**错误信息不说人话，
是失控感的直接来源**。

### 一句话结论

**"对话生图"不是没做，是最后一公里断了**：
工具链、确认文案、确认卡片都在，但
**①预览不显示图、②确认点了不执行、③执行失败甩 SQL**。
用户视角 = "这功能没有"。你的判断是对的。

---

## 一之补二：Google Flow 改版事件（红迪 60+ 条怒评）

> 来源：r/VEO3《Flow's interface has changed, and honestly, they've officially
> nerfed its features.》60+ 评论，**已实抓正文与评论区**。
> 这是本轮**最贴近"界面被改丑"的一手证据**。

用户原话（未翻译，保留原味）：

| 原话 | 说的是什么 |
| --- | --- |
| 「it just feels cluttered. Yes things are more easily accessible but it just feels cluttered.」 | **"东西是更好找了，但就是乱"** |
| 「it is unusable now. it was clunky before… now it is simply unusable. **drag and drop from where? where are the assets?**」 | **"资产在哪？"** |
| 「Es muy poco intuitiva… **no entiendo la lógica**」（非常不直观…我不理解它的逻辑） | **心智模型说不清** |
| 「Upscale is still in there just **buried in a different spot**」 | 功能被埋 |
| 「how is there such a huge update but **the library still a 'work in progress' which barely works**」 | 素材库不可用 |
| 「I feel like this is causing me to have an **anxiety attack**」 | 改版引发的情绪 |
| ✅「all the images in the project are **stored under one sidebar now easily accessible**」 | **资产集中 = 用户唯一点赞的点** |
| ✅「You can also **customize the new interface**… so it looks more like previous one」 | **提供界面密度自定义** |

**注意：这批用户骂的不是"丑"，是"找不到"和"不懂逻辑"。**
这直接反驳了"把界面做好看就行"的思路。

---

## 一之补三：AI 视频工作者的真实疲劳（红迪 60+ 条）

> 来源：r/VEO3《Anyone else feel mentally drained from making AI videos?》
> 60+ 评论，**已实抓正文与评论区**。

| 原话 | 洞察 |
| --- | --- |
| OP：「as soon as a loading pop-up shows up, I end up doing something else」 | 等待期间被迫切任务 |
| 「what OP is describing is the necessity to **constantly task-switch** as one is waiting for a result… a very different mental strain」 | **不是屏幕时间，是被迫切换** |
| 「you can't always work on side tasks… because often, **that work depends on the exact result you'll get from the Gen-AI render**」 | **下游依赖上游 ⇒ 无法并行 ⇒ 只能干等** |
| 「I've worked full-time 5 months on a 50 minute film, and I have yet to find the perfect 'do while you're waiting 1 minute' tasks」 | 等待时间无法有效利用 |
| 「it's taxing trying to figure out the best prompting and dealing with the inevitable screw ups (**one character saying both character's lines**, terrible intonation - and of course **consistency**)」 | 一致性仍是核心痛点 |

**结论：AI 视频工作流的根本痛点不是"生成慢"，是"生成期间用户被锁死"。**
谁能把等待变成可并行、可批量，谁就赢。**我们的任务中心本来就是干这个的。**

---

### 规律 1：所有领先平台都在替用户"锁一致性"，只有我们在让用户现描述

| 平台 | 做法 | 原话 |
| --- | --- | --- |
| LTX Studio | **Elements** | 「define and lock visual parameters—characters, environments, objects—so they appear consistently across every generation。**Instead of describing the same character in every prompt**」 |
| Dashtoon | **角色库映射** | 「我们的 AI 识别你故事里的角色，并把每个角色**映射到我们一致角色库中的角色**，确保每个角色保持一致」 |
| Showrunner | **角色资产** | 上传照片+声音样本+背景故事建角色；用户建的角色成为**社区公共资产** |
| ComfyUI | ❌ 没有 | 社区自嘲：「解决不了，你不能保证模型不出错」 |

**YLCraft 已经有角色库 + 资产中枢，等于"有 Elements 但没有接线"。** 这是最大的机会点：
不是我们缺能力，是**能力没接到生成链路上**。

### 规律 2：局部重生成是"省时间"的关键，不是整段重来

| 平台 | 机制 |
| --- | --- |
| LTX Studio | **Retake**：「change the lighting, adjust the composition, alter a character's expression—**without regenerating the entire shot**」 |
| Showrunner | 删一行台词 → 补一句新台词 → 重新生成 → **新台词自然融入原片** |
| Dashtoon | **Inpainting**，且可"保留原始构图" |
| Runway | Node Execution History，可把历史输出**换回为当前输出**继续往下做 |

### 规律 3：结果历史是一等公民，不是日志

Runway 的 Node Execution History 有五件事：下载 / 全屏灯箱 / **换回当前输出** /
收藏 / 转成独立节点。原话：「lets you easily compare results and restore any
generation **without starting over**」。

对照我们：`step.output` 是一坨 `JSON.stringify`。

### 规律 4：集成度 = 少跳转

- LTX Studio：「Instead of jumping between tools for ideation, scripting, image generation,
  video creation, editing, and delivery, you work inside **one cohesive platform**」
- Showrunner：「与需要分别用 ChatGPT 写剧本、Midjourney 生成图片、Runway 制作视频的
  **割裂式工作流**不同，Showrunner 的优势在于其**垂直整合**」

### 规律 5：入口能低就低

Showrunner 用 **Discord 斜杠命令**，评测原话：「体验过程比想象中要简单得多……
把创作的门槛降到了**会打字就行**的程度」。Dashtoon 用「输入一个故事」当入口。

---

## 一之补四：Agent 类产品（最对症"对话里不出结果"）

> 2026-10-14 补充。**这一类的参考价值高于视频平台** ——
> 我们真正的问题是"对话里该出结果却只给文字"，这正是 Agent 产品的核心命题。

### Claude Artifacts（一手，官方文档）

| 机制 | 原话 / 说明 |
| --- | --- |
| **判断什么该变成产物** | 满足任一条：①显著且自包含（**通常超过 15 行**）②用户想**编辑/迭代/复用** ③**脱离对话上下文仍独立成立** ④用户会**回头再看** |
| 产物位置 | 「opens **beside your conversation**」——开在对话**旁边**，不在对话流里 |
| 集中管理 | 「Everything you make is saved to the Artifacts tab in your Claude sidebar, so you can **find it again from any conversation**」 |
| **指哪改哪** | 「highlight the text you want changed, click 'Edit with Claude'… Claude makes the edit **where you marked it**, so you don't have to describe which section you mean」 |
| **错误旁给修复按钮** | 「look for the '**Try fixing with Claude**' button near the error message」 |
| 分支探索 | 「Edit an earlier message to create a different version of the chat, with its own artifacts, so you can explore another direction **without losing previous work**」 |
| 设计系统注入 | 「Designs and decks can use a **design system**, so new work picks up your colors, fonts, and components」 |

### 其他 Agent 产品（二手，来自他人调研报告）

> 来源：`AI_AGENT_UI_UX_RESEARCH_REPORT.md`（2025-09-18，Claude AI 编制）。
> **属二手转述，未一手核实**，引用时请标注。

| 产品 | 布局 | 要点 |
| --- | --- | --- |
| **Manus** | **双面板**：左对话 + 右"AI 的电脑"实时操作窗口 | 实时看执行步骤；可**暂停/继续/调整**；主打「解决 AI 黑盒问题，建立用户信任」 |
| **Cursor** | IDE 集成 + 侧边面板 + `Cmd+K` 内联生成 | 「在熟悉的界面基础上**渐进式**添加 AI 能力，降低学习成本」 |
| **Replit Agent** | **四面板**：任务/代码/预览/管理 | 实时浏览器测试可视化、可连续自主运行 |
| **AutoGPT** | **任务树** + 执行日志 | 层级化任务管理 |

该报告的几条结论（二手）：
- 「**85% 的成功产品采用分屏式设计**，透明度是建立用户信任的核心」
- 「最成功的智能体产品都在**自动化和用户控制之间找到了平衡点**」
- 趋势：从聊天 → 协作工作台；透明度优先；可控自主性

### 对我们的意义

我们已经是**双栏对话布局**（接近 Manus 模式），方向没错。
缺的是 **Claude Artifacts 那套"产物判定 + 产物独立呈现"**：

| Claude Artifacts 有 | 我们 |
| --- | --- |
| 产物开在对话旁 | ❌ 挤在气泡里 |
| 产物集中可找回 | ⚠️ 素材库存在，但对话里不连通 |
| 指哪改哪 | ❌ |
| 错误旁修复按钮 | ❌ 只给了错误文字 |
| 设计系统注入 | ⚠️ 角色库/资产中枢存在，但**不自动注入** |

---

## 三、已核实条目明细

### YLCraft（读代码，最硬）

| 结论 | 证据 |
| --- | --- |
| 生图/生视频 Agent 工具**已存在** | `backend/app/services/agent/tools/image_tools.py`：`generate_image_asset`、`poll_image_generation_task`；`video_tools.py`：`generate_video_asset`、`poll_video_generation_task`，均 `risk_level="costly"` |
| 对话界面**不渲染图片/视频** | `frontend/src/pages/agent/index.tsx` L303-315 `summarizeToolResult` 把对象压成「返回字段：url、local_path…」；L2557-2561 步骤输出用 `JSON.stringify` 直接显示 |
| 已有专门渲染器先例 | 同文件 L2187 `renderProductionPlanResult(step.tool_name, step.output)` |
| 无产品内教程 | 全前端搜 `onboarding/tour/tutorial/guide` 仅命中 canvas 提示词引导与 previs 相机辅助线 |

### 一手实抓来源

| 平台 | 来源 URL |
| --- | --- |
| LTX Studio | https://ltx.io/blog/ltx-studio-tutorial |
| Runway | https://help.runwayml.com/hc/en-us/articles/45769159004691-Building-your-first-Workflows |
| Showrunner | https://www.pingwest.com/a/307323 （记者第一手实测） |
| Dashtoon | https://insiders.dashtoon.com/dashtoon-studio-august-2024-release/ |
| ComfyUI | https://github.com/Comfy-Org/ComfyUI/issues/6635 |
| Google Flow 改版怒评 | r/VEO3《Flow's interface has changed…》60+ 评论（经 Google 检索命中，已实抓） |
| AI 视频疲劳 | r/VEO3《Anyone else feel mentally drained from making AI videos?》60+ 评论（已实抓） |
| YLCraft 本机实测 | `http://localhost:3000/agent` 实机操作（2026-10-14） |
| V2EX | https://global.v2ex.co/t/1222675 |
| LINUX DO | https://linux.do/t/topic/2438006 |

### 用户痛点原声（中文社区一手）

| 原话 | 出处 |
| --- | --- |
| 「已经修复过无数次提示词，为啥还是出现各种人物角色不一致」 | V2EX |
| 「解决不了，你不能保证模型不出错」 | V2EX |
| 「先把人物角色的全身图片生成出来定义好，然后再让视频模型使用这个人物图片素材生成视频」 | V2EX（**用户自发得出"角色固化"结论**） |
| 「用户的 size 以及质量要求并非硬性指令，模型会内部自行决定」 | LINUX DO |
| 「我让其生成 16:9，最终得到的比例是 1672×941」 | LINUX DO |
| 「去 response 了就会自动路由」 | LINUX DO |
| 「GUI Should Simplify, Not Complicate」 | ComfyUI #6635 |
| 「if you start wanting to go even slightly beyond simple usage, you will inevitably find yourself turning to ComfyUI's modular approach」 | ComfyUI 评论 |

---

## 四、自问自答：这就可以了吗？

### 问：表格填完就够了吗？
**不够。** 还有三个硬缺口：

1. **我们自己那一行还是"读代码"推的，不是"用"出来的。**
   我没有真正点过一遍 YLCraft。步骤数、必填项两格仍然空着，只有我能实测才能填。
2. **没有"用户在哪一步放弃"的数据。** 步骤数只说明成本，不说明流失点。
3. **缺"独占能力"对照。** 我们的世界地图、剧情时间线、小说→世界提取，
   上面这些平台**一个都没有**。表格只比了人家强的地方，没比我们强的地方，
   照着改会把自己改成"又一个 LTX Studio"。

### 问：那还需要什么？
- **需要 YLCraft 实测**：要么你开给我看，要么我用浏览器走一遍我们自己的实例。
- **需要你提供一个真实卡点**：你自己用的时候哪一步最烦。这个我搜不到。
- **需要决定改造顺序**：见下。

### 问：搜这么多，会不会跑偏成"抄别人"？
**有风险，必须刹车。** 上面 5 条规律里，**规律 1 和 2 我们是"缺接线"，不是"缺能力"**；
规律 3、4、5 是通用体验，照抄无害。真正该做的是**把已有能力接上**，
而不是再堆新功能。

---

## 五、对 YLCraft 的落地结论

按"改动小 × 收益大"排序：

| 优先级 | 改动 | 对应规律 | 依据 |
| --- | --- | --- | --- |
| **P0** | **修「确认执行」点了不生效** —— 这是功能不可用的根因 | 实测 | 实测卡在 `waiting_confirmation`；两个同名按钮 |
| **P0** | 对话里**渲染图片/视频结果**（缩略图+点击看大图+存入素材库） | 规律 3 | 实测只有 `返回字段：success、normalized_request、visual_plan、` |
| **P0** | 生图预览**显示 visual_plan**，别只给字段名 | 规律 3 | 同上 |
| **P0** | **错误信息说人话**，不甩 SQL | Flow 改版教训 | 实测甩出 `badly formed hexadecimal UUID string` |
| **P1** | 生成时**自动注入角色卡/资产**，不让用户重复描述 | 规律 1 | LTX Elements / Dashtoon 角色映射 |
| **P1** | **局部重生成**（只改一个镜头/一句台词，不整段重来） | 规律 2 | LTX Retake / Showrunner |
| **P1** | 生成结果**历史**：可对比、可回滚、可收藏 | 规律 3 | Runway Node Execution History |
| **P1** | **批量/排队，把等待变成可并行** | AI 疲劳证据 | 「that work depends on the exact result」 |
| **P2** | 资产集中可见（Flow 用户唯一点赞的点） | Flow | 「stored under one sidebar now easily accessible」 |
| **P2** | 降低入口门槛（一句话/一个故事起步） | 规律 5 | Dashtoon Story Mode |
| **P2** | 产品内引导 | — | 我们目前完全没有 |

**重要提醒：P0 里前四条全是"修断掉的线"，不是"做新界面"。**
Flow 的教训是：**用户骂的是"找不到"和"不懂逻辑"，不是"丑"。**
所以别急着改视觉，先把断掉的链路接上 —— 否则换了皮肤，功能还是不能用。

**P0 第一条（确认按钮不生效）需要先复现确认**，因为不排除是我点击问题。
复现方法：在 `/agent` 发送生图指令 → 点顶部待确认横幅的「确认执行」→
看 Run 状态是否从 `waiting_confirmation` 变化。
