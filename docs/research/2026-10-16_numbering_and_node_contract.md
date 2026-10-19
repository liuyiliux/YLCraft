# 深度补充：handraw-style 编号体系 / OhMyGame 节点契约（2026-10-16 第二轮）

> 🚨 **证据等级**：本文内容全部来自**一手文档**（README / SKILL.md / docs），
> **我没有看到这三个项目的真实界面**（都是桌面软件，需下载安装）。
> 文档里描述的交互设计 =「作者这么写的」，**不等于**「我亲眼看到」。
>
> 其中 **OhMyGame `authoring.md` 里有 ASCII 布局示意图**（作者画的），
> 这是本文唯一的"布局图"来源 —— **它是示意图，不是截图**。

> 上一轮只读了三个项目的 README。**这轮把"里面的实际做法"挖出来了** ——
> 编号体系的组织格式、skill 的路由写法、节点模型的双术语机制。
> **这些是能直接抄的工程做法，不只是"看看人家怎么做"。**

---

## 〇、这轮挖到的东西（都是可抄的具体做法）

| # | 从哪来 | 挖到什么 |
| --- | --- | --- |
| 1 | handraw `skills/` | **13 个 skill 的命名与组织法** |
| 2 | handraw `SKILL.md` | **根 skill = 路由索引**，操��契约在子目录；路由用中文触发短语 |
| 3 | handraw `STYLES.md` | **331 种风格的分组 + 条目固定结构**（含负向约束） |
| 4 | handraw `COLORS.md` | **按"情绪"而非"色相"分组**；每色带一句文案 + 中英双名 |
| 5 | OhMyGame `playable-nodes/` | **引擎术语 ↔ 编辑器术语双术语机制** |
| 6 | OhMyGame `playable-nodes/` | **"只有一种节点类型"，其余都是 preset** |

---

## 一、handraw-style 的 skill 组织法（可直接抄）

### 1.1 13 个 skill，全是「动词 + 产物」命名

```
article-cover-designer          文章封面设计
article-illustration-planner    长文配图规划
couple-photo-orchestrator       情侣写真编排
custom-asset-manager            自定义素材管理
handdraw-style-prompter         ★ 风格提示词生成（入口）
handraw-browser-producer        浏览器端制作
handdraw-jianying-producer      剪映端制作
handraw-video-producer          视频制作
handraw-volc-tts                火山 TTS
ip-designer                     IP 设计
knowledge-video-director        ★ 知识视频导演
poster-prompt-generator         海报提示词生成
style-fusion-prompter           风格融合
style-library-importer          风格库导入
tweet-style-importer            推文风格导入
```

**后缀是产物类型**：`-prompter` 出提示词 / `-producer` 出成片 /
`-designer` 出设计 / `-planner` 出规划 / `-orchestrator` 出编排 / `-importer` 出导入。

> **对比我们的 `backend/app/skills/`**：命名风格一致（`comic-image-prompt`、
> `storyboard-generation`、`character-visual-card`），
> **但我们没有 `-producer`（成片）、`-orchestrator`（编排）这类"最终产物"角色**。
> 我们的 skill 大多是"生成某类内容"，缺"把内容接成一条流水线"的角色。

### 1.2 🔴 根 SKILL.md 只是「入口 + 路由索引」

> 「This is the **install entrypoint** for the complete hand-drawn style package.
> …the **operational contract** is `skills/handdraw-style-prompter/SKILL.md`.
> **Before handling a request, read that Skill file completely.**」

**根文件负责路由，子文件才是操作契约。** 结构上和我们一样。

### 1.3 🔴 路由用「用户会说的话」触发

> 「When the user asks to **设计文章封面、视频封面、生成封面提示词**、
> 创建**公众号封面**、设计 X/社交封面…（例如"**给文章做封面**"、
> "**文章封面设计**"、"**视频封面设计**"）」

**直接把中文触发短语列出来**，而不是只写抽象能力描述。

> **这条对我们有直接价值** —— 我们的 skill `description` 写得偏"能力"，
> **没有列用户实际会说的话**，导致 Agent 容易路由不到。

### 1.4 它的安全边界写法（3 条都很硬）

| 边界 | 原文 |
| --- | --- |
| 不下载演示素材 | 「Skill installation must **not** download demo videos or **private episode media**」 |
| 不依赖作者机器 | 「Bundled source/resources and separately installed tools/services are distinct; **never rely on the author's workstation**」 |
| 密钥不进仓库 | 「Its client is bundled; **secrets stay in encrypted per-user configuration outside the repository** and Skill installation」 |

**还保留门禁**：「Keep **confirmed-plan and reviewed-input gates**」

### 1.5 又一条「别瞎承诺」

> 「**Read [package dependencies] before claiming that an installed Skill can
> generate or render media.**」

**—— 跟第 5 条元规则是同一件事。**

---

## 二、handraw-style 的编号体系（解决"生成漂移"的工程做法）

### 2.1 🔴 风格按「题材」分 8 大类

| 编号 | 分类 | 数量 | 适用（原文） |
| --- | --- | --- | --- |
| **FA** | 国际社论幽默 | 40 | 「日常幽默、讽刺随笔、都市观察与生活吐槽」 |
| **FB** | 经典绘本叙事 | 66 | |
| **FC** | 现代平面艺术 | 32 | |
| **FD** | 日本当代插画 | 42 | |
| **FE** | 新国风与传统工艺 | 67 | |
| **FF** | 3D黏土毛毡与纸雕 | 17 | |
| **FG** | 动漫和赛璐璐 | 23 | |
| **FH** | 先锋实验与综合媒介 | 44 | |

> **总计 331 种。分组依据是「题材/气质」，不是「技法」** ——
> 用户是按"我要什么感觉"找，不是按"我用什么笔触"找。

### 2.2 每个编号的固定结构（这张表就是范本）

```markdown
| 预览图 | 编号 | 英文名 | 参考来源 | 核心视觉特征 |
| :---: | :---: | :---: | :---: | :---: |
| ![](images/individual/FA/FA-001.webp) | **FA-001** <small>(#001)</small>
| Playful Deadpan Doodle | 参考: Gemma Correll
| 松散黑线、怪萌人物、少量点色、白底、日常吐槽与尴尬幽默；
  人物轮廓优先于细节堆砌…表情偏冷脸、尴尬或突然夸张，
  姿态要有明确喜剧节奏，**避免统一的可爱微笑**。 |
```

**四个可抄的设计点：**

1. **双编号并存**（`FA-001` 新号 + `#001` 旧号）—— 兼容历史用法
2. **标注参考艺术家**（Gemma Correll / Saul Steinberg / James Thurber）—— **溯源**
3. **特征用 `<details>` 折叠** —— 331 条也不显得臃肿
4. 🔴 **特征描述里带「负向约束」** ——「**避免统一的可爱微笑**」

**第 4 点是解决"生成漂移"的关键**：光说"要什么"不够，
**还得说"不要什么"**。这跟我们 skill 里的「negative_prompt 是必填」是同一思路，
但它把负向约束**写进了风格定义本身**，而不是让用户每次另外写。

### 2.3 🔴 色号按「情绪」分组，不按色相

| 编号 | 分组 | 情绪定位（原文） | 适合题材 |
| --- | --- | --- | --- |
| 1 | 经典蓝系 | 「**沉静理性**、跨越时光的纯粹蓝调」 | 科技、思考、静夜、海洋 |
| 2 | 清新绿系 | 「**自然治愈**、盛夏微风的清新绿意」 | 生活方式、健康、植物、轻食 |
| 3 | 古典红绿 | | |
| 4 | 浪漫粉紫 | | |
| 5 | 暖阳大地 | | |
| 6 | 中性色系 | | 36 色 / 6 组 × 6 色 |

### 2.4 每个颜色 = 编号 + 中文名 + 一句文案 + 中英双名

```
C-01 · 克莱因蓝
      「纯粹之蓝 通向无限」        ← 文案（给用户感受）
      提示词：`主题色：克莱因蓝（Klein Blue）。`   ← 中英双名给模型
```

**四个字段各司其职**：编号（查）、名（说）、文案（选）、提示词（喂模型）。

> 💡 **「文案」这个字段是我们完全没有的**。给风格/场景配一句 evocative 的短句，
> 既帮助用户选择，也降低了"名字看不懂"的门槛。

---

## 三、OhMyGame 的节点模型（方法论最清晰的一份）

> 来源：`docs/playable-nodes/README.md`，一手全文。

### 3.1 🔴 三条核心边界（原文）

> 1. **Nodes own presentation and input. The Runtime owns state and flow.**
>    「在节点内部，浏览器能做的都允许；节点之间，状态、导航、存档和资源都走 Runtime」
> 2. **One node type.**
>    「菜单、场景、选项、档案、结局**都只是预设（preset），不是运行时类别**」
> 3. **Agent first.**
>    「作者主要通过**描述**创建节点，而不是选择节点类型或写代码」

**第 1 条是架构命门**：**边界清楚，就不会长成屎山。**

### 3.2 🔴🔴 双术语机制（本轮最值得抄的一条）

> 「**编辑器给作者看更朴素的词。**
> 代码、schema、工具和其他文档**保留引擎术语**。」

| 引擎术语（内部） | 编辑器术语（给用户） |
| --- | --- |
| Scene | **Node** |
| Exit | **Signal**（+ 路由它的边） |
| Exit with Allow Back | `push` 边 |
| Template | **Preset** |
| Replay | **Restart** |
| History | 返回栈 |
| Select | 选元素 |

> **这是"界面在说人话"的教科书做法** —— 不是把内部术语翻译一下，
> 而是**两套术语分别维护，各服务各的人**。

### 3.3 Signal / Edge 的设计

| 名词 | 定义（原文） |
| --- | --- |
| **Signal** | 一个节点报告的**命名结果**，如 `open-archive` |
| **Edge** | 从一个节点的 Signal 到另一个节点的连接 |
| **Navigation Exit** | `role: navigation` 的 Signal；**在画布上有名字，不用画线** |
| **`when`** | Signal 的触发条件，一行描述；**仅显示，不执行** |

**「Navigation Exit 有名字就不用连线」** = 减少视觉噪音；
**「when 仅显示不执行」** = 不给用户看伪代码。

---

## 四、对我们的意义

### 4.1 可以直接抄的四条

| # | 抄什么 | 从哪来 | 我们的差距 |
| --- | --- | --- | --- |
| 1 | 🔴 **引擎术语 / 用户术语分开维护** | OhMyGame | 我们界面直接暴露内部术语（`source_node_id`、`relation: sequence`…） |
| 2 | 🔴 **风格/场景定义里写死负向约束** | handraw | 我们风格定义偏"要什么"，缺"避免什么" |
| 3 | **给每个风格/场景配一句 evocative 文案** | handraw COLORS | 我们完全没有 |
| 4 | **skill 描述里列用户会说的话** | handraw 根 SKILL | 我们写的是能力描述 |

### 4.2 一条更根本的

**第 1 条（双术语）可能是我们"界面丑 + 不在点"的一个隐藏成因** ——
**当界面直接暴露内部结构术语时，用户看到的是"系统怎么实现的"，而不是"我要做什么"。**

这跟我们之前发现的「`返回字段：success、normalized_request、visual_plan、`」
是同一个病：**内部词汇泄漏到了用户界面**。

### 4.3 一个可落地的具体动作

我们已有 `THEME` 场景色（`THEME.ecommerce` / `photography` / `drama` / `coser`），
但**只有 4 个、只有内部 key、没有编号、没有文案、没有中英双名提示词**。

按 handraw 的四字段（编号 / 名 / 文案 / 提示词）补齐，
成本很低，但能让「风格选择」从"猜 key"变成"按感觉挑"。

---

## 五、待核实

| 项 | 状态 |
| --- | --- |
| handraw 331 种风格的实际出图质量 | `未测`（只看了图鉴结构） |
| `handdraw-jianying-producer` 怎么对接剪映 | `未看` |
| `handdraw-video-producer` 的成片流程 | `未看` |
| OhMyGame `authoring.md`（编辑器体验） | `未看` |
| OhMyGame `vision.md`（为什么重构固定节点模型） | `未看` |
| 我们的界面是否暴露了内部术语 | `未系统核查`（已有个别实例） |
| 场景色扩展到编号+文案的成本 | `未评估` |