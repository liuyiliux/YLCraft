# Toonflow 拆解：一个已经做完的「我们」（2026-10-19）

> <https://gitee.com/HBAI-Ltd/Toonflow-app>
> **915 star · 354 fork · 28 个版本（v2.0.6）· MIT 许可 · Gitee GVP**
> 一句话：**开源 AI 短剧、漫剧与视频创作平台。**

---

## 一、先说最重要的一句

**Toonflow 做的东西 = 我们这三小时讨论的东西 —— 无限画布 + 节点 + Agent + 资产库 + 剧集流程。**

而且它：
- ✅ **MIT 许可**（可闭源商用）
- ✅ **已完成**（v2.0.6，28 个版本迭代）
- ✅ 桌面 + Android + Docker + 服务器
- ✅ 21 种界面语言
- ✅ 插件市场 + MCP + A2A

**所以我们要诚实面对一个问题：差异化在哪？**（第六节回答）

---

## 二、它是什么

> Toonflow 是面向短剧、漫剧和短视频创作者的开源 AI 创作工具。
> 通过**无限画布**编写剧本与分镜、**管理角色和场景素材**、生成图片与视频。
> 支持本地部署、自由接入模型，并可通过 **AI Agent、MCP 与插件**扩展创作流程。

### 官方四条创作流程

1. **编写剧本与分镜** —— 在文本节点里整理故事、人物设定、镜头描述，LLM 辅助，人工审阅
2. **准备角色与场景素材** —— 导入参考图，或用图片生成节点做角色/场景/分镜图
3. **生成视频镜头** —— 连接文本与图片参考，选视频模型，按镜头生成
4. **预览、整理与下载** —— 在无限画布中预览组织，下载后继续处理

> 🔴 **注意它自己说**：「**创作者需要审阅和调整内容**」——
> 它不是全自动，是「AI 出 + 人改」。这跟我们的定位一致。

---

## 三、🔴 架构：这是最有价值的部分

### 3.1 仓库结构（Bun monorepo）

```
apps/
  web          前端
  server       后端
  desktop      桌面端（electrobun）
  mobile       Android
  updateServer 更新服务器

packages/
  nodes/*      🔴 节点（8 个，每个是独立包）
  tools/*      🔴 Agent 工具（10 个）
  teams/*      多智能体
  ext/*        插件
```

### 3.2 🔴 八个节点：**内容节点**和**生成节点**分开

| 内容节点（承载） | 生成节点（生成） |
| --- | --- |
| `textNode` 文本 | — |
| `imageNode` 图片 | `imageGenerationNode` 图片生成 |
| `videoNode` 视频 | `videoGenerationNode` 视频生成 |
| `audioNode` 音频 | `audioGenerationNode` 音频生成 |
| — | 🔴 `director3dNode` **3D 导演台** |

**这个拆分很讲究：**

```
imageNode          = 一张图放在画布上（可以是上传的、也可以是生成的产物）
imageGenerationNode = 一个"生成器"，有参数、会花钱、会跑
```

> 🔴 **对照我们**：我们的 `CanvasNode` 把"内容"和"生成器"混在一起了
> （`image` 节点既承载图又是产物，`image_model` 是生成器但类型不同构）。
> **Toonflow 的拆法更干净：内容节点是数据，生成节点是算子。**

### 3.3 🔴 十个 Agent 工具 —— 这解决了我们最大的设计空白

```
askUser          问用户
assetOperator    操作素材库
browser          浏览器
canvas           🔴 操作画布
ffmpeg           音视频处理
mediaGeneration  媒体生成
skillOperator    操作技能
webFetch         抓网页
webSearch        搜网页
workspace        工作区
```

**`canvas` 是一个 tool** —— 意思是：

> **Agent 不是"在旁边看着"，它能直接操作画布（加节点/改参数/连线/删除）。**

**`assetOperator`** —— Agent 能查/取/存素材。
**`skillOperator`** —— Agent 能调用技能（对应我们说的"模板/Skill"）。

> 🔴 **对照我们**：我们 `backend/app/api/v1/agent.py` 的 `ChatRequest` **只有 `message: str`**，
> Agent 完全没有画布操作工具。**这是必须补的一层。**
> 这也解释了我们 v9 那个"Agent 侧栏"为什么感觉空 —— **它没手**。

### 3.4 插件化节点（加节点不改核心）

`packages/nodes/*` 每个节点是独立包，`packages/ext/*` 是扩展。
有**插件市场**（api.toonflow.net/console/plugIn）。

> 这正好是我们反复说的"**加新用途 = 加模板/加节点，不改代码**"。

### 3.5 画布引擎：Vue Flow

`package.json` 里：
```json
"patchedDependencies": {
  "@vue-flow/core@1.48.2": "patches/vueFlowCore.patch"
}
```

**它用 Vue Flow 做节点画布，还打了补丁。**

> 💡 这印证了「节点画布用成熟库 + 打补丁」是可行路线。
> 我们是 React，对应的是 **`@xyflow/react`（React Flow）**，同一个作者、MIT、38,705 star。
> **之前我倾向"继续改 basketikun/infinite-canvas"，Toonflow 这个数据点值得重新考虑。**

### 3.6 其它能力

| 能力 | 说明 |
| --- | --- |
| 🔌 **MCP** | 接外部工具 |
| 🤖 **A2A** | Agent 间协作，开放提示词/工具 |
| 🧩 插件市场 | 扩展节点、工具 |
| 🔧 自由接模型 | 第三方 API / 本地 ComfyUI / 本地 LLM |
| 🏠 本地部署 | 数据在自己设备 |
| 🌐 21 种语言 | |

### 3.7 从截图目录看它有什么

- 项目首页与灵感创作
- 创作画布（深色 / 浅色主题）
- **角色、场景与道具资产**
- 🔴 **3D 导演台与镜头预演**
- 角色三视图与图片生成
- 多参考素材视频生成
- 🔴 **节点菜单与分组操作**
- 插件市场

---

## 四、技术栈对照

| | Toonflow | 我们 YLCraft |
| --- | --- | --- |
| 语言 | TypeScript 全家桶 | Python 后端 + TS 前端 |
| 运行时 | **Bun** | Node / Python |
| 前端 | Vue（Vue Flow） | **React 18 + Ant Design 5** |
| 后端 | Bun Server | **FastAPI + SQLModel + Postgres** |
| 画布 | Vue Flow | 自研 `InfiniteCanvasSurface` |
| 部署 | 桌面/Android/Docker | Docker |
| 许可 | **MIT** | ？（见许可审计） |

**我们和它的最大差别：我们有后端业务（素材库/项目/角色/API 网关），它是本地优先工具。**

---

## 五、必须补的（对照清单）

| # | 缺什么 | Toonflow 对应 | 优先级 |
| --- | --- | --- | --- |
| 1 | 🔴 **Agent 的画布操作工具** | `canvas` / `assetOperator` / `skillOperator` | **最高** |
| 2 | 🔴 **视频节点 + 视频生成节点** | `videoNode` / `videoGenerationNode` | 高 |
| 3 | 🔴 **音频节点 + 音频生成节点** | `audioNode` / `audioGenerationNode` | 高 |
| 4 | **内容节点 / 生成节点分离** | 8 个节点两两对应 | 中高 |
| 5 | **3D 导演台** | `director3dNode` | 中（全新概念） |
| 6 | 插件化节点 | `packages/nodes/*` | 中 |
| 7 | 节点打组 | 节点菜单与分组操作 | 中（LibTV 也有） |
| 8 | MCP | MCP | 低（先不碰） |

---

## 六、🔴 那我们的差异化在哪（诚实面对）

Toonflow 已经做完，而且 MIT。**我们必须回答"为什么还要做"。**

### 三个可能的差异化

| # | 差异化 | 依据 |
| --- | --- | --- |
| **1** | 🔴 **降低门槛** —— 它自己承认"创作者需要审阅和调整"，说明它还是**工具**，不是**助手** | 我们 `DESIGN.md` 第一条约束；LibTV 用户吐槽"看不懂文档" |
| **2** | 🔴 **资产中枢** —— 它是"项目内素材"，我们是**跨项目的素材资产中枢 + 角色/场景一致性** | 它有"角色/场景/道具资产"，但看不出跨项目复用 |
| **3** | 🔴 **中文内容行业深度** —— 我们有平台采集、素材库、项目/剧本/角色体系（44 个页面） | 它没有平台侧能力 |

### 反过来，它的优势我们要认

- 桌面/Android 本地部署
- 21 种语言
- 插件市场
- 3D 导演台
- 已经迭代 28 个版本

---

## 七、建议怎么用它

### 选项 A：参考架构，自己实现（推荐）

抄它的**架构判断**（内容/生成节点分离、Agent 工具体系、插件化），不抄代码（虽然 MIT 允许）。

**理由**：我们技术栈不同（React vs Vue），整体移植成本高于重写。

### 选项 B：直接用它的节点设计

它的 8 个节点定义是**公开的 TypeScript 接口**，可以读来对齐我们的节点模型。

### 选项 C：跑起来看

它支持 Docker：
```sh
git clone https://github.com/HBAI-Ltd/Toonflow-app.git
cd Toonflow-app
docker compose up -d --build
# 访问 127.0.0.1:3000
```
**但这个环境 Docker 拉镜像有问题**（阿里云镜像 403，之前踩过）。

---

## 八、我建议下一步

| # | 动作 | 理由 |
| --- | --- | --- |
| 1 | **读它的 8 个节点定义源码** | 直接对齐我们的节点模型，省很多设计 |
| 2 | **读它的 10 个 tool 定义** | 这是 Agent 的"手"，我们最缺 |
| 3 | 看它的 3D 导演台实现思路 | 全新概念，值不值得做 |
| 4 | 重新评估画布引擎（Vue Flow vs React Flow vs 现在的） | 它打了补丁说明有坑 |

**要不要我继续读它的源码？** 我建议读 1 和 2 —— 那是纯 TypeScript 接口，读完能直接改我们的设计。

---

## 九、一句话总结

**Toonflow 证明了我们的方向是对的，也证明了我们慢。**

**但它没解决"降低门槛"** —— 它自己说"创作者需要审阅和调整"，LibTV 用户说"看了文档还是不会"。

**这正好是我们的位置。**
