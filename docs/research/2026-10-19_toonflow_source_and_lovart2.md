# Toonflow 源码 + Lovart 2.0 实测（2026-10-19）

> 两件事一起记：
> 1. **Toonflow 的节点与 Agent 工具源码**（回答"Agent 的手"怎么设计）
> 2. **Lovart 2.0 当天上线**的实测文章（回答"主动式 Agent"长什么样）
>
> 这两份合起来，几乎把我们前面所有设计问题都回答了。

---

# 第一部分：Toonflow 源码拆解

## 1. 八个节点的源码结构

| 节点 | src 下的文件 |
| --- | --- |
| **textNode** | `index.vue` `markdownContent.ts` `markdownEditor.vue` `markdownExtensions.ts` `markdownPreview.vue` |
| **imageNode** | `index.vue` 🔴 `imageInpaint.ts`（局部重绘）🔴 `imageLighting.ts`（打光）🔴 `imageMultiAngle.ts`（多角度）🔴 `imagePanorama.ts`（全景）`useImageVariationNode.ts`（变体） |
| **imageGenerationNode** | `index.vue` + `components/` |
| **videoNode** | `index.vue` `videoProcessing.ts` |
| **videoGenerationNode** | `index.vue` + `components/` |
| **audioNode** | `index.vue` `audioProcessing.ts` `audioWaveform.ts` |
| **audioGenerationNode** | `index.vue` `audioSettings.ts` |
| **director3dNode** | `index.vue` 🔴 `agentPrompt.ts` 🔴 `agentTools.ts` `scene.ts` `mannequin.ts` `motion.ts` `sceneAnimation.ts` `renderMedia.ts` `lightDirection.vue` `directorPanel.vue` `directorTour.vue` `sceneEditor.vue` |

### 🔴 两个重大发现

**发现 1：`imageNode` 里已经实现了我们讨论过的所有图片操作**

```
imageInpaint.ts      局部重绘
imageLighting.ts     重新打光   ← 我们一直说"必需但没设计"
imageMultiAngle.ts   多角度
imagePanorama.ts     全景扩展
useImageVariationNode.ts  变体
```

**这些不是生成节点的参数，是"内容节点自己的编辑能力"。**
→ **图片节点的编辑功能是内置在节点里的，不走 Agent。**

**发现 2：`director3dNode` 自带 `agentPrompt.ts` + `agentTools.ts`**

**每个节点可以给 Agent 提供自己的工具和提示词。**
→ 节点不只是画布上的一块，它是**一个可被 Agent 操作的专业工具面**。

---

## 2. 🔴 端口类型模型（比我们的完整）

```ts
export type NodeDataType =
  | "STRING" | "INT" | "FLOAT" | "BOOLEAN"
  | "IMAGE" | "MASK" | "LATENT"        ← ComfyUI 体系
  | "AUDIO" | "VIDEO" | "FILE"
  | "MODEL" | "CLIP" | "VAE" | "CONDITIONING"
  | "*"
  | (string & {});                      ← 允许自定义扩展
```

```ts
export type NodeHandle = {
  id: string;
  type: "source" | "target";
  dataType: NodeDataType | NodeDataType[];   // 🔴 一个端口可以是多种类型
  label?: string;
};
```

```ts
export function isTypeCompatible(sourceType, targetType) {
  // '*' 通配符 或 数组里任意一个相同 → 兼容
}
```

```ts
export type NodeOptions = { label?, icon?, handles?: NodeHandle[], outputs? };
export type NodeData = { label?, handles?, outputs? };
```

**对照我们**：

| | Toonflow | 我们 |
| --- | --- | --- |
| 类型 | 14 种（含 MASK/LATENT/CLIP/VAE/CONDITIONING） | 5 种（text/image/asset/json/any） |
| 多类型端口 | ✅ `dataType: NodeDataType[]` | ❌ 单值 |
| 通配符 | ✅ `"*"` | ✅ `any` |
| 可扩展类型 | ✅ `(string & {})` | ❌ 枚举 |

> 💡 **`MASK` / `LATENT` / `CONDITIONING` 我们不需要**（那是 ComfyUI 的中间态），
> 但 **`AUDIO` / `VIDEO` / `FILE` 必须有**，而且**多类型端口**值得抄（一个端口能接图也能接视频）。

---

## 3. 🔴 18 个画布操作 —— Agent 的"手"

`packages/tools/canvas/src/runtime.ts` 定义了 18 个操作，全部暴露成 Agent 工具：

| # | 操作 | 中文名 | 类型 |
| --- | --- | --- | --- |
| 1 | `getCanvas` | 画布概览 | 读 |
| 2 | `findCanvasNodes` | 查找画布节点 | 读 |
| 3 | `getCanvasNodes` | 读取节点详情 | 读 |
| 4 | `getCanvasEdges` | 读取画布连线 | 读 |
| 5 | `getNodeTools` | 查询节点函数 | 读 |
| 6 | `addCanvas` | 新增画布 | 写 |
| 7 | `switchCanvas` | 切换画布 | 写 |
| 8 | `renameCanvas` | 重命名画布 | 写 |
| 9 | `addNode` | 新增节点 | 写 |
| 10 | `deleteNodes` | 删除节点 | 写 |
| 11 | `moveNodes` | 移动节点 | 写 |
| 12 | **`renameNodes`** | **重命名节点** | 写 |
| 13 | `connectNodes` | 连接节点 | 写 |
| 14 | `deleteEdges` | 删除连线 | 写 |
| 15 | `selectNodes` | 选择节点 | 写 |
| 16 | `arrangeCanvas` | 整理画布 | 写 |
| 17 | `fitCanvas` | 适应画布 | 写 |
| 18 | `nodeTools` | **调用节点函数** | 执行 |

### 设计要点

**① 读写分开，渐进式读取**
```
getCanvas(概览) → findCanvasNodes(查找) → getCanvasNodes(详情) / getCanvasEdges(连线)
```
提示词明说：「**getCanvas 仅返回概览；按任务范围使用 findCanvasNodes、getCanvasNodes…分批处理仅保留摘要和游标**」

> 防的是：一次把整个画布 JSON 塞进上下文，token 爆炸。

**② `getNodeTools` + `nodeTools` = 节点自带能力摘要**
Agent 先查"这个节点有什么函数"，再调。**节点是可扩展的执行面。**

**③ 系统提示里有一条硬约束**
> 「通过运行中的画布操作工具控制激活画布，**不要直接修改画布 JSON**。」

> 💡 对照我们：**我们 Agent 根本没有画布工具**（`ChatRequest` 只有 `message`）。
> 要补的就是这 18 个（可以先补 8 个核心的）。

---

## 4. 十个 Agent 工具的分工

| 工具 | 职责 |
| --- | --- |
| `canvas` | 画布操作（18 个，见上） |
| `assetOperator` | 全局素材库 |
| `skillOperator` | Skill（技能） |
| `mediaGeneration` | 生成图/视/音 |
| `workspace` | 工作区文件 |
| `browser` | 浏览器 |
| `ffmpeg` | 音视频处理 |
| `webSearch` / `webFetch` | 联网 |
| `askUser` | 反问用户 |

### 4.1 `mediaGeneration` 的四个工具

| 工具 | 说明 |
| --- | --- |
| `generateImage` | 提示词 + 可选**工作区参考图** → 图片 |
| `generateVideo` | 提示词 + 参考图/视频/音频/**首尾帧** → 视频；可设模式/时长/分辨率/音频 |
| `generateAudio` | 文本/提示词 + 参考图/音频 → 音频；可设音色/语速/音量/语种/采样率/格式 |
| 🔴 `listMediaModels` | **先查可用模型**，返回 providerId / modelId / 类型 / 模式 / 支持的画幅·时长·分辨率·音色 |

**`listMediaModels` 的描述里有一句硬规定**：
> 「**生成前先查询，不能猜测模型 ID。**」

> 💡 **这是防幻觉的工程手段**：不让模型猜模型名。
> 我们做"模型选择"时应该照抄 —— **先查再用**。

### 4.2 `assetOperator`：8 个动作 + 版本号防冲突

| 动作 | 说明 |
| --- | --- |
| `list` | 分页查询（返回 nextCursor） |
| `read` | 读文本 / 图片 / Office / PDF / EPUB / CSV → 转 Markdown；**返回 revision** |
| `create` | 新建，不覆盖 |
| `update` | 用完整文本替换；**必须用最近一次 read 返回的 revision** |
| `mkdir` / `move` / `delete` | 目录操作，不覆盖 |
| 🔴 `import` | **把全局素材复制到当前工作区** |

**关键概念区分（提示词里写死的）：**
> 「全局素材库与**当前工作区 assets 文件夹**属于不同范围。」
> 「全局素材用作画布图片或生成参考时，**先 import 复制到当前工作区**。」

**还有 `readOnly` 模式**：只允许 list / read / import。

> 💡 **revision 防冲突机制**：改文件必须先读、带着版本号改，冲突就重读。
> 我们有类似机制吗？没有的话该加。

### 4.3 `skillOperator`：这就是 DESIGN.md 说的「Skill 运行时」

| 动作 | 说明 |
| --- | --- |
| `list` | 返回技能目录 |
| `read` | 读 SKILL.md 或 references 文件 |
| `create` | 新建技能/资料，不覆盖 |
| `update` | 用完整内容修改 |

**scope**：`workspace`（当前工作区）| `global`（全局）

**硬规定**：
> 「新建技能先创建 **SKILL.md**，必须包含 **name 和 description 的 YAML frontmatter**。」

🔴 **这是 Claude Code 的 skill 格式，被用在产品里。**

**提示词里的工作流（很值得抄）：**
> 「**每次接到任务，先用 skillOperator(action=list) 检查技能名称和描述。任务匹配技能时，先用 action=read 读取 SKILL.md 再开始实质工作**；`disableModelInvocation=true` 的技能仅在用户明确指定时读取使用。」

**权限开关**：`allowRead` / `allowCreate` / `allowUpdate`

---

## 5. 🔴 director3dNode：节点自带 Agent 工具的最佳样本

### 它给 Agent 的工具只有两个

| 工具 | 说明 |
| --- | --- |
| `readDocument` | 读取本轮**独立草稿**的 scene / plan；可按 objectId / joint / path 精确读；可读 schema |
| `editDocument` | **原子批量修改**草稿；`add` / 删 / 改；数组下标 `-` 表示追加 |

### agentPrompt 里的规则（每一条都值得抄）

| 规则 | 原文 |
| --- | --- |
| **只改该改的** | 「只修改本次指令涉及的内容，**保留其他对象、动作和镜头**」 |
| **历史只读** | 「历史方案只读，最终草稿会保存为一个**新方案**，id 由应用分配」 |
| **先读再改** | 「先读取摘要及需要修改的片段，必要时通过 readDocument 查 schema」 |
| **不许猜** | 「按 objectId 定位…**不要猜数组下标**」 |
| **原子性** | 「一个 operations 批次**整体生效或整体失败**；相互依赖的修改应放在同一批」 |
| 🔴 **自验证** | 「**结束前必须通过 readDocument 读取检查结果，确认 `valid` 为 true；没有修改成功不能声称完成**」 |
| **多模态引用** | 「多模态内容中的 `{{ref N}}` 对应输入引用列表第 N 项」 |

### 🔴 那条自验证规则是重点

> 「**结束前必须读取检查结果，确认 valid 为 true；没有修改成功不能声称完成。**」

这正面回答了我们之前讨论的「Agent 谎报完成」。

**它的解法不是"让 Agent 更诚实"，是"让工具返回可验证状态，Agent 必须读它"。**

| 方案 | 靠什么 |
| --- | --- |
| ❌ 我的 v10 自检 chip | 靠 Agent 自觉声明 |
| ✅ Toonflow | **靠工具返回 `valid:true`，且规定必须读** |

> 💡 **这比我们在对话里写"我确认了"强一个量级** —— 因为它有**机器可验证的返回值**。

---

## 6. 插件化架构（加东西不改核心）

```
packages/
  nodeScaffold     节点脚手架（节点契约）
  toolScaffold     工具脚手架
  teamScaffold     多智能体脚手架
  extScaffold      扩展脚手架
  nodes/*          节点插件
  tools/*          工具插件
  teams/*          团队
  ext/*            扩展
```

**每个节点/工具都是独立包，有自己的 package.json。**
→ 这就是"**加新用途不改核心代码**"落地的方式。

---

# 第二部分：Lovart 2.0 实测（文章要点）

> 来源：《Lovart 2.0大版本升级，现在它会主动替你干活了》网黑哥，2026-10-19 09:59
> Lovart 2.0 **今天上线**

## 1. 核心：个人设计 Agent「Arti」

**定位：Personal Agent 在垂直领域的玩法。**

解决的真问题（作者原话）：
> 「用 AI 最头疼的就是：项目换了，对话重新开了，自己的喜好也得重新介绍一遍。喜欢什么颜色，图片拿来干什么，哪些排版不要用，**明明前面讲过，下回还得再来**。」

**Arti 怎么了解你**：
1. 学习你过往在 Lovart 的项目
2. 通过对话获取

**都存进记忆**，下次开新项目不用重新解释。

---

## 2. 🔴 五个主动式功能

### 2.1 设计委托（可定时 + 限额）

> 「把一件完整的设计任务交给 Arti…**也可以安排时间，到点再执行**。」
> 「**执行一次还是定期重复，每次最多花多少积分，都可以自己设**。」
> 「需要你定方向的地方，还是由你确认。」

### 2.2 设计调研（带来源报告 + 分阶段计划）

> 「Arti 会搜集资料、分析参考，再整理成一份**带来源的报告**。」
> 「报告里也把**要做的具体工作、建议动作和优先级**列了出来。」
> 「后面还列了**分阶段执行计划**，接下来先做什么、再做什么。」

作者的关键经验：
> 「**最好的提示词还是给它一个案例。**」

### 2.3 🔴 画布巡检（我们的"自检"应该这样落地）

> 「**这个画布巡检就是帮你检查画面和要求有没有对上，发现问题会给出提醒。**
> 尤其是一套图，**单张看着还行，放到一起就可能发现字体、风格不一样，就等于是有一个兜底的质检。**」

**实测发现了真问题**：
> 「回到画布一看，**目录刊名里的「好」字，跟封面上的笔迹没对上**。」

**入口**：点对话框上方 Arti →「开始画布巡检」「开始调研」

🔴 **这直接回答了我 v10/v11 纠结的"自检 chip"问题**：

| | 我的做法 | Lovart 的做法 |
| --- | --- | --- |
| 形态 | 对话里贴 chip | 🔴 **独立的"巡检"动作** |
| 时机 | 每次生成后自动 | **用户主动点，或 Agent 提议** |
| 范围 | 单张图 | 🔴 **一整套图的一致性** |
| 输出 | 一句声明 | **具体问题列表 + 定位** |

**"一套图放到一起才看得出不一致" —— 这是单图自检永远发现不了的。**

### 2.4 反馈改稿（多人协作）

> 「可以把作品分享给别人审阅，**让对方直接在图上评论**，Arti 再把意见整理出来，**提出修改方案，确认后执行**。」

### 2.5 Skill 自进化

> 「把反复做过的工作，**总结成以后能继续调用的方法和流程**。」
> 例子：做旧刊改编 → 先查原刊、再定版式、最后检查封面和目录，**这套流程有重复使用价值**

---

## 3. 作者的结论（对我们最有用的一句）

> 「**Arti 的重点，是让平台对你的了解能够接着用，而且是主动替你去干活，
> 就是你还没张嘴呢，它提前就把活给你干了。**」
>
> 「把**重复介绍背景、整理要求的时间**省下来，就能多花点心思在作品上。」

---

# 第三部分：结论 —— 我们要改什么

## 1. 🔴 必须补：Agent 的"手"（18 个画布操作）

**这是最大的空白。** 我们 `ChatRequest` 只有 `message`。

**建议先做 8 个核心的**：

```
读：getCanvas / findCanvasNodes / getCanvasNodes / getNodeTools
写：addNode / connectNodes / renameNodes / nodeTools
```

> `renameNodes` 要早做 —— LibTV 用户被"图片节点1.2.3.4.5"逼疯过。

## 2. 🔴 自检改成「画布巡检」

| 我的 v10/v11 | 应该改成 |
| --- | --- |
| 对话里贴「✓原图保留 ⚠效果你亲眼看」 | **独立的「巡检」动作**，扫一整套图 |
| 单图检查 | **跨图一致性检查**（字体/风格/角色） |
| Agent 声明 | **给具体问题 + 定位到哪张图的哪个部分** |

## 3. 生成前必须 `listModels`

**不许猜模型 ID。** 这能直接减少"模型不存在/鉴权失败"这类错误（我们踩过）。

## 4. 素材库要加 revision（防冲突）

`read` 返回 revision，`update` 必须带。**多个人/多个 Agent 同时改才不会互相覆盖。**

## 5. Skill 用 SKILL.md + frontmatter

不用自己发明格式。**Claude Code 的 skill 格式已经是事实标准**，Toonflow 也用了。

## 6. 节点拆成「内容节点」+「生成节点」

```
imageNode（承载图）    vs  imageGenerationNode（生成器）
videoNode（承载视频）  vs  videoGenerationNode
```

**内容节点带自己的编辑能力**（`imageInpaint` / `imageLighting` / `imageMultiAngle` / `imagePanorama`）。

## 7. 3D 导演台要"取长补短"

用户说我们之前做过导台。Toonflow 的做法：
- 低多边形**关节人偶**（`objType: "mannequin"`，身高 1.8，+Y 上 +Z 前 +X 左）
- **scene 共享，plans 只存动画与运镜**
- Agent 用 `readDocument` / `editDocument` 操作**本轮私有草稿**
- 历史方案**只读**，改完存成**新方案**，id 由应用分配
- `hiddenParts` 隐藏关节及下游部位

> 这套「**共享 scene + 多方案 diff + 草稿隔离**」比"每个方案一份完整场景"省得多，
> 也天然支持"在方案间对比运镜"。**建议对照我们的导台取这个优点。**

---

## 待办（建议顺序）

| # | 做什么 | 依据 |
| --- | --- | --- |
| 1 | 设计 Agent 画布工具（8 个核心） | Toonflow 18 个操作 |
| 2 | 加 `listModels` 前置查询 | Toonflow 硬规定 |
| 3 | 巡检功能（跨图一致性） | Lovart 画布巡检 |
| 4 | 节点拆内容/生成 | Toonflow 节点结构 |
| 5 | 素材库 revision | Toonflow assetOperator |
| 6 | Skill 用 SKILL.md 格式 | Toonflow skillOperator |
| 7 | 3D 导台取「共享 scene + 多方案」 | Toonflow director3d + 我们已有导台 |
