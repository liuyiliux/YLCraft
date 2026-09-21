# YLCraft 参考项目文档

> 来源：联网搜索 + 本地代码分析，2026-05-03

***

## ArcReel — AI Agent 视频工作台

**GitHub**: <https://github.com/ArcReel/ArcReel>\
**技术栈**: React 19 + FastAPI + Claude Agent SDK + Claude/Gemini/Seedream + FFmpeg + SQLite/PostgreSQL

### 核心能力

- **完整流水线**：上传小说 → AI 拆分剧本 → 生成人物设计图 → 生成分镜图 → 生成视频片段 → FFmpeg 合成成片
- **多智能体协作**：基于 Claude Agent SDK，编排 Skill + 聚焦 Subagent，自动 dispatch 专职 Agent（角色提取/剧本生成/资产生成）
- **多供应商可切换**：图片支持 Gemini / Seedream / Grok，视频支持 Veo 3.1 / Seedance / Grok，不锁定单一供应商
- **角色一致性**：先生成人物设计图，后续所有分镜和视频均参考该设计，跨镜头保持角色外观统一
- **剪映草稿导出**：按集导出为剪映 ZIP，桌面版里二次编辑
- **异步任务队列**：RPM 速率限制 + Image/Video 独立并发通道，lease-based 调度，支持断点续传

### YLCraft 可借鉴

- Backend Provider 架构（Protocol + Registry）
- 多供应商切换机制
- 角色一致性保证策略爆款拆解
- 异步任务 + SSE 进度推送

***

## CutClaw — 音乐驱动 AI 长视频剪辑

**GitHub**: <https://github.com/GVCLab/CutClaw>\
**技术栈**: 多智能体 + 多模态模型

### 核心能力

- **音乐驱动剪辑**：先分析音乐节拍/重拍/能量曲线，把视觉叙事严格对应到听觉骨架上
- **一键素材解构**：原始视频和音频提取镜头、场景、动作、情感等层级信息
- **指令驱动剪辑风格**：文字指令自动理解并执行剪辑决策
- **智能自动裁剪**：内容感知裁剪，适配 9:16/16:9 等各平台比例
- **多智能体协作**：编剧（理解叙事）+ 剪辑师（选择时间戳）+ 审片（质量验证）
- **多模型支持**：可接入主流多模态模型

### YLCraft 可借鉴

- 多智能体 Pipeline 模式
- 音乐驱动的自动剪辑策略
- 素材解构与重组逻辑

***

## LocalMiniDrama — 本地 AI 短剧漫剧生成工具

**GitHub**: <https://github.com/xuanyustudio/LocalMiniDrama>\
**技术栈**: Node.js + Seedance2 生图

### 核心能力

- **本地 AI 短剧生成**：从故事到成片一站式，数据不出本机
- **角色生成**：输入 outline → LLM 提取角色 → 返回角色数组（name/role/description/personality/appearance/voice\_style）
- **角色肖像生成**：character.appearance + drama style → imageClient.generateImage()
- **短剧工作流管理**：剧本 → 角色 → 分镜 → 生图 → 生视频 → 剪辑

### YLCraft 可借鉴

- **角色生成流程**（最直接可复用的参考）：outline → LLM → 角色数组
- **角色肖像生成**：appearance 字段作为 prompt 生成图片
- 短剧全链路设计思路

***

## huobao-drama（火宝短剧）

**GitHub**: <https://github.com/chatfire-AI/huobao-drama>\
**技术栈**: Go + Vue3 + SQLite

### 核心能力

- **全栈 AI 短剧自动化生产平台**：剧本解析 → 角色/分镜生成 → 视频合成
- **角色管理**：AI 生成角色形象，批量生成，图片上传与管理
- **分镜制作**：自动生成分镜脚本，场景描述与镜头设计，分镜图片生成（文生图）
- **本地存储 + SQLite**：适合自建的 AI 素材/分镜/视频任务管理后台

### YLCraft 可借鉴

- 角色批量管理功能设计
- 分镜脚本自动生成逻辑
- 本地存储方案

***

## NarratoAI — AI 脚本 + TTS 流水线

**参考目录**: `F:\PycharmProjects\YLCraft-refs\NarratoAI`
**技术栈**: Python + MoviePy + LLM + TTS

### 核心能力

- **Pipeline 模式**：多步骤流水线，视频素材搜索 → LLM 旁白生成 → TTS 配音 → 视频合成
- **脚本生成**：从视频分析生成纪录片风格脚本
- **TTS 集成**：文本转语音，多音色支持
- **Prompt 模板**：预设各类脚本 prompt 模板

### YLCraft 可借鉴

- Pipeline 模式设计
- TTS 集成方式
- Prompt 模板化

***

## jellyfish — 视频处理 API

**参考目录**: `F:\PycharmProjects\YLCraft-refs\jellyfish`
**用途**: 视频处理 API 规范设计参考

### YLCraft 可借鉴

- 视频 API 接口设计
- 任务状态管理

***

## yiliu（逸流）— 多平台图文生成器

**GitHub**: <https://github.com/liuyiliux/CrossGen>
**技术栈**: Python 3.11+ + FastAPI + Redis + Vue 3 + TypeScript + Element Plus

### 核心能力

- **一键生成**：一句话输入，自动生成多平台图文内容（小红书/抖音/公众号/头条号）
- **灵感获取**：搜索小红书热门内容，支持链接解析，导入参考图片
- **AI 驱动**：集成 GPT/Claude 等 LLM + Stable Diffusion 图像生成
- **批量处理**：支持批量主题并行生成
- **模板化**：平台模板配置，灵活响应平台规则变化
- **结构化内容**：总标题 + 总文案 + 多张图片的内容结构

### YLCraft 可借鉴

- **图文分离的数据结构**：Outline (title + copywriting) + Page (image\_prompt)，适合 YLCraft 的 story outline 设计
- **平台模板系统**：不同平台有不同模板（platform\_templates.yaml），YLCraft 场景标签（电商/摄影/短剧/COSER）可参考
- **参考图导入**：小红书笔记图片直接导入作为 AI 绘图参考，精准还原风格

***

## XHS\_ALL\_IN\_ONE — 小红书全栈运营工具

**GitHub**: <https://github.com/cv-cat/XHS_ALL_IN_ONE>\
**技术栈**: React + TypeScript + Ant Design + Python + FastAPI

### 核心能力

- **账号矩阵管理**：多账号绑定、Cookie 管理、健康巡检
- **多种登录方式**：二维码扫码 + 手机验证码 + Cookie 导入，用 `Segmented` 分段控件切换
- **Drawer 抽屉式交互**：添加账号用右侧抽屉（`AddAccountDrawer`），比 Modal 更沉浸
- **账号健康巡检**：每个账号有独立「检查」按钮验证 Cookie 有效性
- **多平台扩展**：通过 `platform-selector` 支持平台切换

### 前端组件结构

```
frontend/src/
├── pages/platforms/xhs/
│   └── accounts-page.tsx           # 账号矩阵页面
├── components/account/
│   ├── add-account-drawer.tsx      # 添加账号抽屉
│   ├── qr-login-panel.tsx          # 二维码登录面板
│   ├── cookie-import-panel.tsx     # Cookie 导入面板
│   └── phone-login-panel.tsx       # 手机验证码登录面板
├── components/layout/
│   └── platform-selector.tsx       # 平台选择器
└── pages/platform-select/
    └── platform-select-page.tsx    # 平台选择页面
```

### YLCraft 已借鉴

- ✅ **Drawer 抽屉式添加账号** — 替代 3 个独立 Modal，更沉浸
- ✅ **Segmented 分段控件** — Cookie/扫码/浏览器三种方式切换
- ✅ **健康检查按钮** — 每个连接卡片独立「检查」按钮
- ✅ **账号矩阵概念** — 页面标题改为「账号矩阵」
- ✅ **统计栏** — Row + Col + Statistic 展示账号状态
- ✅ **QR 登录面板** — 二维码居中 + 状态提示 + WebSocket 自动轮询
- ✅ **Cookie 导入面板** — Textarea + 校验 + 导入

***

## infinite-canvas — 开源无限画布工作台

**GitHub**: <https://github.com/basketikun/infinite-canvas>
**许可证**: AGPL-3.0
**技术栈**: React 19 + Vite 7 + Ant Design 6 + Zustand + TanStack Query + Tailwind + lucide + motion

### 核心能力

- 多画布管理：同一工作区内可维护多个画布。
- 无限画布交互：节点拖拽、缩放、平移、网格背景、视口变换。
- 关系连线：节点间可建立连接，配合选择框、上下文菜单使用。
- 视图辅助：小地图、导入导出、撤销重做。
- 画布助手：Agent 不直接写 UI 状态，而是输出画布操作流。

### YLCraft 可借鉴

- 视口模型：`{ x, y, k }` 表示平移和缩放，所有节点放进 world layer 后统一 transform。
- 鼠标点缩放：wheel 时以指针位置为锚点计算新视口，避免缩放后内容跳走。
- 背景网格：按视口偏移和缩放绘制，强化空间感。
- 节点数据模型：`id/type/title/position/width/height/metadata`，保持节点内容和布局分离。
- Agent ops 模型：Agent 输出 `add_node`、`update_node`、`delete_node`、`connect_nodes`、`select_nodes`、`set_viewport`、`run_generation` 这类操作，前端或服务端统一 apply。

### 采用边界

不能直接复制源码进 YLCraft，除非项目整体接受 AGPL-3.0 传染义务。当前策略是只借鉴架构和交互模式，自行实现轻量无限画布组件。YLCraft 现有 `/story` 中的“关系图谱”不是这个自由画布，它只展示项目事实和血缘关系。

***

## 其他参考项目

| 项目                        | GitHub                        | 核心特点                                     |
| ------------------------- | ----------------------------- | ---------------------------------------- |
| **Toonflow**              | HBAI-Ltd/Toonflow-app         | AI 短剧工厂，小说秒变剧集，无限画布工作台                   |
| **BigBanana AI Director** | —                             | 关键帧驱动，Script-to-Asset-to-Keyframe 工业化工作流 |
| **Micro-Drama-Skills**    | zhaihao118/Micro-Drama-Skills | Claude Skills 驱动，AI 短剧全流程自动化             |
| **MoneyPrinterTurbo**     | —                             | AI 视频配音/文案                               |
| **CineGen-AI**            | Will-Water/CineGen-AI         | 开源 AI 漫剧/动漫/短剧生成                         |
| **Yihen-Drama**           | CszYihen/Yihen-Drama          | 前端+后端+Docker 一键部署，支持角色场景                 |

***

## 参考项目能力矩阵

| 功能          | ArcReel | CutClaw | LocalMiniDrama | huobao-drama | NarratoAI | XHS\_ALL\_IN\_ONE |
| ----------- | ------- | ------- | -------------- | ------------ | --------- | ----------------- |
| 小说→短视频      | ✅       | ❌       | ✅              | ❌            | ❌         | ❌                 |
| 音乐驱动剪辑      | ❌       | ✅       | ❌              | ❌            | ❌         | ❌                 |
| 角色生成/生图     | ✅       | ❌       | ✅              | ✅            | ❌         | ❌                 |
| 分镜生成        | ✅       | ❌       | ✅              | ✅            | ❌         | ❌                 |
| 视频合成        | ✅       | ✅       | ✅              | ✅            | ✅         | ❌                 |
| 多智能体        | ✅       | ✅       | ❌              | ❌            | ❌         | ❌                 |
| 多供应商切换      | ✅       | ❌       | ❌              | ❌            | ❌         | ❌                 |
| TTS         | ✅       | ❌       | ❌              | ❌            | ✅         | ❌                 |
| 剪映导出        | ✅       | ❌       | ❌              | ❌            | ❌         | ❌                 |
| 本地部署        | ✅       | ✅       | ✅              | ✅            | ✅         | ✅                 |
| 账号矩阵管理      | ❌       | ❌       | ❌              | ❌            | ❌         | ✅                 |
| Cookie 自动获取 | ❌       | ❌       | ❌              | ❌            | ❌         | ✅                 |
| 二维码登录       | ❌       | ❌       | ❌              | ❌            | ❌         | ✅                 |
| 健康巡检        | ❌       | ❌       | ❌              | ❌            | ❌         | ✅                 |

***

## YLCraft 下一步可复用功能优先级

1. **\[高] 角色生成服务**：参考 LocalMiniDrama 的 `characterGenerationService.js`，从剧本描述用 LLM 提取角色信息
2. **\[高] 角色肖像生成**：参考 LocalMiniDrama 的 `characterLibraryService.js`，从 appearance 生成图片
3. **\[高] 多供应商 Backend**：参考 ArcReel 的 Provider 架构，完善 BackendManager
4. **\[中] 角色一致性策略**：参考 ArcReel，锁定角色设计图保证跨镜头一致
5. **\[中] 音乐驱动剪辑**：参考 CutClaw，实现 Beat-based 自动剪辑
6. **\[中] Cookie 自动获取**：参考 XHS\_ALL\_IN\_ONE 的二维码登录 + 浏览器获取，完善 CookieManager 适配
7. **\[低] 剪映草稿导出**：参考 ArcReel，按集导出剪映 ZIP

***

## 新增参考：AI 视频导演与预演工作流

### updream — 3D 预演台

**文章参考**: <https://hub.baai.ac.cn/view/57229>

#### 核心启发

- 通过 3D 预演先确定人物站位、动作路线和镜头关系，减少生成视频反复抽卡。
- 预演不是专业 DCC 替代品，而是生成前的空间控制层。
- “先摆空间事实，再提交生成请求”与 YLCraft 的 `PrevisSceneDocument`、Asset Hub 引用和截图回流设计一致。

#### YLCraft 采用边界

- 保留独立预演场景，不把空间状态塞进 `ProjectContent`、Canvas 或通用 `Model3DViewer`。
- 先完成静态节点、相机和参考截图，再评估动态运镜与视频导出。
- 参考其产品价值，不复制实现或供应商接口。

***

### Wasserman's Filmmaker Suite — AI-native 电影制作套件

**GitHub**: <https://github.com/wassermanproductions/wassermans-filmmaker-suite>

#### 核心能力

- `ScriptBreak`：脚本拆解。
- `Cork Board` / `Master Canvas`：参考资料和生产编排。
- `Blockout`：基础 3D 走位与构图。
- `Motion Previs Studio`：动态预演。
- `Storyboard Reference Studio`：分镜参考管理。
- `Circle Take`、`Stem Studio`、DaVinci MCP：镜头筛选、声音拆分和后期交接。

#### YLCraft 可借鉴

- Blockout 对应当前预演台的 `primitive` + `human_proxy` 节点。
- Motion Previs Studio 对应后续 Phase 2 的 24fps、关键帧和播放头。
- 把脚本、走位、参考、生成、剪辑和声音拆成可交接模块，支持阶段性验证；不做一个大而全的 DCC 页面。
- 预演输出应该是带 provenance 的参考资产，而不是复制一份分镜事实。

#### 许可边界

仅借鉴公开产品形态和工作流；引入源码前必须单独核对仓库当前许可证和依赖许可。

***

### BigBanana AI Director — 本地 ComfyUI 视频导演链路

**GitHub**: <https://github.com/shuyu-labs/BigBanana-AI-Director>

#### 核心启发

- 用本地 ComfyUI 承接图像/视频生成，降低云端 API 按量成本和供应商锁定。
- 多图参考、工作流节点和导演控制结合，适合把角色、场景、构图参考一起送入生成链路。
- 本地模型能力应是 Provider/Connector 的一种后端，不应改变项目内容和 Asset Hub 的事实边界。

#### YLCraft 可借鉴

- 预演截图进入现有图片/视频请求时，保留 `previs_scene_id`、`camera_id`、场景 revision 和源资产 provenance。
- 后续可把 ComfyUI 作为配置驱动的本地 Provider 接入，不在 Story 或预演台写死工作流节点。
- 参考图数量、尺寸和模型能力要由连接器契约约束，避免把大图或不兼容参考直接塞给供应商。

#### 许可边界

仅参考本地工作流和多图参考的产品思路；是否可复用源码、工作流和模型配置，以仓库许可证及各模型许可证为准。

***

## 新增调研：3D 预演参考项目 · 入口形态与素材许可

> 调研日期：本会话。来源：GitHub 源码与 README 实际抓取核对，非摘要转述。

### 入口形态对比

| 项目 | 入口形态 | 进入方式 | 证据 |
| --- | --- | --- | --- |
| storyai-3d-director-desk | 独立顶级工作台 | 根页面即 3D 导演台（无路由嵌套、无上级业务页） | `src/App.tsx` 直接渲染 `DirectorDeskShell` |
| awplanet | 独立桌面应用（Electron） | 独立启动，进入即项目/场景编辑器 | README |
| kunpeng-director | 本地优先独立应用 | 独立启动，进入即 3D 白模舞台 | README |
| open-storyboard-canvas | 画布内节点 | 在无限画布新建"导演台"节点，截图可送回画布 | README「导演台与全景」 |
| costage | Codex MCP widget | 对话中说"打开当前项目的 CoStage"，原生 3D widget 全屏打开 | README |

结论：参考项目没有把 3D 预演做成业务页的二级按钮；主流是独立顶级工作台（storyai/awplanet/kunpeng）、画布节点（open-storyboard-canvas）或 Agent 环境内嵌（costage）。YLCraft 应给 `/previs` 增加顶级导航入口，保留分镜卡片快捷入口。

### 素材许可对比

| 项目 | 人形素材 | 许可证 | 能否直接用于 YLCraft |
| --- | --- | --- | --- |
| storyai | UE 小白人 `ue-mannequin-retopology.glb`（Sketchfab，作者 William Luque）+ 程序化人形/姿势预设（纯代码） | 仓库 MIT；GLB 为 Sketchfab Standard | GLB 可下载商用但保留署名、不能单独打包转售；程序化人形/姿势代码 MIT 可直接参考复用 |
| awplanet | 角色骨骼、物件库（几何/建筑/室内/城市/地形） | PolyForm Noncommercial 1.0.0 | 不可商用，只借鉴思路 |
| kunpeng-director | 白模/灰模道具 + 56 类动作模板 + 28 类运镜模板 | MIT | 可复用（保留版权声明） |
| open-storyboard-canvas | `blueprint-figure.glb`（2.1MB 蓝图人形） | MIT（二开 Storyboard-Copilot，须保留 NOTICE 署名） | 可下载（保留 NOTICE）；全景无内置 |
| costage | 8 个真实 GLB 角色（健硕/纤细/儿童/二头身等） | 仓库无 LICENSE 文件（默认 All Rights Reserved） | 不可再分发，不建议下载使用 |

背景/全景：5 个项目均无内置全景素材，都是用户导入或 AI 生成。YLCraft 走"用户导入 + 生图生成全景"，或引 CC0 图库（如 Poly Haven）。

### 采用建议

1. 人型占位首选程序化生成（胶囊+球+方块组合成人形，可摆姿势）——参照 storyai `ProceduralMannequin`（MIT）与 kunpeng 白模思路，无版权风险。
2. 真实人形 GLB 可选 storyai UE mannequin（Sketchfab Standard 保留署名）或 Mixamo 免费角色（Adobe 条款允许商用）。
3. costage GLB 与 awplanet 素材禁用（无许可 / Noncommercial）。
4. 入口对齐参考项目主流：`/previs` 加顶级导航入口。

***

### shotblock — AI 分镜 3D 规划（浏览器，与预演台高度同向）

**GitHub**: <https://github.com/shanghaicellcenter/shotblock>\
**在线**: <https://shanghaicellcenter.github.io/shotblock/>

#### 核心能力

- **15-DOF 关节级人形**：9 个一键姿势预设 + 逐关节滑杆（头/躯干/肩/肘/髋/膝），姿势描述自动进提示词
- **GLB 角色导入** + 内嵌 CC0 来源链接（poly.pizza / Kenney / Quaternius）
- **真实镜头数学**：传感器格式 → 真实 FOV、超焦距/景深读数、构图预设（EWS…ECU/OTS/双人/POV/插入）
- **5 机位对话覆盖生成**（master + OTS×2 + CU×2）、A/B 机位移动、关键光预设（9 种）、180°/30° 规则实时告警
- **Animatic 播放**（24fps 时间码，WebM 导出）、6 联分镜纸导出、AI-ready 提示词（Veo 3 / Runway Gen-4 / Kling / Luma / Sora 2）
- **一致性参考包**：每角色三视图 + 每镜帧 + 提示词 + shot-list JSON，喂给视频模型锁定形象与站位

#### YLCraft 可借鉴

- 程序化人形做到"关节级滑杆 + 姿势预设"是预演台 Phase 2 方向（当前是预设姿势，可加逐关节微调）
- CC0 人形来源结论：poly.pizza / Kenney / Quaternius
- 镜头数学、180° 规则、覆盖生成是导演台的"专业感"加分项，可与截图回流同批评估
- 一致性参考包 = YLCraft 截图回流 + 分镜参考的成品形态

***

### YLCraft 内置人形模型（仓库内资产）

| 文件 | 来源 | 许可 | 使用边界 |
| --- | --- | --- | --- |
| `frontend/public/models/ue-mannequin.glb` | Sketchfab（作者 William Luque，经 storyai 仓库） | Sketchfab Standard | 可商用、保留署名、不得单独打包转售/再分发；许可见 `frontend/public/models/LICENSE-UE-MANNEQUIN.txt`。**已下线但文件保留**（见下） |
| ~~`frontend/public/models/vanguard.glb`~~ | open-storyboard-canvas（MIT 二开 Storyboard-Copilot） | MIT | **已删除**（连同 `LICENSE-VANGUARD.txt`，2.16MB，不再随构建产物发布）；上游 MIT 允许重新引入，需要时按普通模型从素材库添加 |
| 胶囊人（程序化） | storyai ProceduralMannequin 思路自写 | 无外部依赖 | 可摆姿势，无版权风险；**目前是唯一的载体** |

**2026-09-19 人形占位载体收敛（`previs-agent-scene-composition` 已确认项）**：人形占位**只剩程序化胶囊人一种载体**。三条结论按发生顺序：① `vanguard.glb` 是带具体造型的角色模型，会把无关的形状与颜色暗示传给下游生成模型，**移出选项且文件已删除**；② 默认配色由彩色改为**中性中灰**——影响下游识别的是人形与背景的**明度对比**，同对比度下中灰比纯白更稳（纯白易被读成"白衣/白皮肤"，且打光下高光溢出会糊掉形体结构）；③ `ue-mannequin.glb` **也随之下线**：实测它自带 **0 条动画**（`animations: []`，73 节点 / 1 蒙皮 / 67 关节），而参数型动作驱动的是胶囊人的 16 个关节通道，选中它只能站着不动——"能选却动不了"比没有这个选项更像 bug。**文件与许可记录保留**，待"参数型动作烘焙成 GLB"落地后接回来：它是仓库里唯一的带蒙皮人形，是验证蒙皮变形与穿模的唯一载体（胶囊人是刚性零件拼的，验证不了这件事）。历史场景里记录的 `metadata.proxyStyle`（`ue` / `vanguard`）一律忽略并按通用人形渲染。

***

## 新增调研：预演动作与运镜模板来源（`previs-agent-scene-composition` tasks 1.8）

> 调研日期：2026-09-19。方法：**读本地仓库源码逐文件核对**（`YLCraft-refs/kunpeng-director`、`YLCraft-refs/storyai-3d-director-desk`），不采信 README 摘要——两处 README 口径与源码实测不一致的地方下面都标了。
> **一句话结论：两者都不含可导入的动作数据；它们是"自写动作"的加速器（词表、时长口径、曲线写法、运镜清单）。**

### 许可

| 项目 | 许可 | 边界 |
| --- | --- | --- |
| kunpeng-director | MIT（Copyright (c) 2026 Qiaopengfei，`LICENSE`） | 可商用、可修改，保留版权声明 |
| storyai-3d-director-desk | MIT（Copyright (c) 2026 YZ，`LICENSE`） | 同上；其 UE 小白人 GLB 另有 Sketchfab Standard 约束（见上表） |

### kunpeng-director：58 类动作 + 28 类运镜，**全部是参数化生成，不是骨骼动画**

- 动作模板 `packages/core/src/motionTemplates.ts` **只有元数据**：`id / label / category / description / defaultDurationSec / moving / suggestedDistance`，**没有任何关节数值**。
- 关节数值由 `packages/core/src/playback.ts` 的 `animatedJoints(action, progress, durationSec)` **算出来**：正弦驱动 + 首尾 envelope 淡入淡出，例（walk）：`hipL.x = sin(2π·progress·cycles)·28·envelope`、`kneeL.x = max(0, −sin)·48·envelope`；`cycles = durationSec × 频率`（走 1.35、快走 1.8、跑 2.3 步/秒）。
- 关节词表 **11 个**（`types.ts` 的 `JointName`）：`hips / spine / neck` + 左右 `shoulder / elbow / hip / knee`——**含我们缺的 `spine` 与 `neck`**。
- 分类 8 类，实测条目数 **58**（基础 5 / 走位 8 / 视线 6 / 交流 7 / 手部 11 / 姿态 8 / 情绪 4 / 专项 9）；README 声称 56，**按 README 会漏 2 条**。
- 运镜模板 `cameraTemplates.ts` **恰好 28 条**（与 README 一致），且不是死关键帧：`createCameraKeyframes(shot, move)` 从机位起点 / 注视点 / FOV 推算出整段关键帧，覆盖 dolly-zoom（机位与焦段反向）、whip-pan（甩镜并在目标处制动）、handheld（手持噪声）等。
- 另有 `createMotionKeyframes`：把一段动作转成 5 个关键帧（0 / 0.18 / 0.5 / 0.82 / 1，标注「起势 / 动作峰值 / 收势」），并带位移路径与朝向联动（`pathYaw`）。

### storyai：20 个姿势预设，控制键 **30 个**（比我们的 16 通道多出躯干 / 头颈 / 重心 / 手脚）

- `src/editor/presets/mannequinPosePresets.ts`：姿势是 `controls: Record<string, number>`——**语义化的相对角度字典**（`leftShoulder.spread`、`leftHip.pitch`、`leftKnee.bend`…），与我们自写胶囊人时的思路同源（当初就是按它 MIT 的分层关节思路自写的）。
- 预设 20 个（`src/editor/schema/poseSchema.ts` 的 id 白名单同源）：stand / t-pose / walk / run / sit / crouch / kneel-one / kneel-two / hands-on-hips / lean / bow / think / fight / kick / throw / push / wave / reach / cross-arms / phone。
- 实测用到的控制键 **30 个**：`body.offsetY / body.pitch / body.roll / body.yaw`、`torso.pitch / torso.yaw`、`head.pitch / head.roll / head.yaw`、左右 `Shoulder.pitch/spread/twist`、左右 `Elbow.bend`、左右 `Hip.pitch/spread`、左右 `Knee.bend`、左右 `Foot.pitch/roll`、左右 `Hand.pitch/roll/twist`。

### 结论与可用清单

1. **没有"可导入的动作数据"**：两个项目都不含 FBX / BVH / GLTF 动作文件，也不含骨骼动画曲线。真正要"导入骨骼动画"，仍须另开 change 走 `carrier=bone`（**引用式**：复用既有带动画的模型资产 + 动作名，不新增二进制存储，见 `previs-agent-scene-composition` 数据归属判定）。
2. **可照抄的是词表与口径**（对齐语义、不引代码，符合本任务"不引入外部代码"的约束）：
   - **动作清单与 8 类分类 + 中文标签 + 默认时长 + 是否位移 / 建议位移距离** → 直接作为我们动作资产的 `category` 取值、命名与 `duration_seconds` 口径；
   - **步频口径互补**：kunpeng 是"动作自带固定步频"（1.35 / 1.8 / 2.3 步每秒），我们是"步频 = 速度 ÷ 步幅"由位移反推——两者可同时在（前者定动作节拍，后者防滑步）；
   - **28 类运镜清单与参数化生成思路** → 我们相机侧此前只有手打关键帧，**这是本次核对里最直接的增益点**。**2026-09-19 已落地 26 类**（`frontend/src/pages/previs/cameraMoves.ts`，tasks 6.6–6.9 / design D12）：沿用了它的 8 个分类与强度档位（克制 / 标准 / 强烈）口径，**滚转类两条未纳入**（我们的机位没有滚转通道，加它要动通道契约——宁可少两条也不要"选了看不出效果"）；仍是参数化生成关键帧、仍不引代码；
   - **storyai 的 30 个控制键** → 我们的通道缺口清单（见下条）。
3. **发现的真实缺口：先补通道，再扩条数。** 我们的参数型动作当时只有 16 个通道（左右肩各 3 + 左右肘 + 左右髋各 3 + 左右膝），**没有躯干、没有头颈、没有重心偏移**。后果很具体：kunpeng 的「视线」6 条与「交流」7 条里相当一部分（低头 / 抬眼 / 回望 / 点头 / 摇头 / 鞠躬）与 storyai 的 crouch / lean / bow / think **当时根本做不出来**——加了动作条目也做不出来。顺序必须是"补通道 → 再按词表扩动作"。
   **→ 2026-09-19 已按此结论落地（`previs-agent-scene-composition` tasks 1.9 / design D11）**：通道 16 → **23**（新增 `torso.0/1/2`、`head.0/1/2`、`bodyOffsetY` 整体重心升降）；**照抄了本节的两份词表口径**——分类沿用（新增动作归入「视线 / 交流 / 姿态 / 情绪」），符号沿用 kunpeng 的"前倾/低头为正"（我们的中线部位与之同旋向，故数值不必反号），并补了第二批 9 条动作：`look-down` 低头 / `look-up` 抬眼 / `look-side` 侧头张望 / `look-back` 回望 / `nod` 点头 / `shake-head` 摇头 / `bow` 鞠躬 / `ponder` 沉思 / `crouch` 半蹲。   **仍然没有引入任何外部代码或素材**，只对齐了语义与口径。

***

## 新增调研：外部 AIGC 工作台与"视频转动作"流水线（2026-09-20）

> 来源：用户提供的两篇公众号文章（非仓库）。
> **证据等级低于上一节**：上一节是读本地仓源码逐文件核对，本节**只有文章正文**，无法核对源码；
> 凡属作者自述的参数（版本号、硬件、权重体积、套餐消耗）一律标注"**自述**"，不作为决策依据。

### A. 《我手搓了一个 AIGC 工作台…》（作者：可爱的小Cherry，2026-09-18）

**它是什么**：个人 DIY 的漫剧（AIGC 短剧）创作工作台，自述完成度约 60%，已跑通"创意 → 分集 → 分镜 → 资产 → 分镜图"的**静态素材**链路。与我们**同赛道但不同段位**：它停在"分镜图"，我们这一期做的是"分镜 → 可动 3D 预演 → 参考图/参考视频"。

| 它的模块 | 与我们的关系 | 结论 |
| --- | --- | --- |
| **导演预演包**：分镜 → JSON 镜头语言 → **交给 Blender** 运镜与建模（自述"偏文戏、较粗糙、未适配动作戏"） | 与我们的 `generate_previs_draft`（分镜格 → 受限操作集 → 浏览器内 3D 预演）**目标相同、落地方式相反** | **方向被外部印证**。它的短板（文戏向、未适配动作戏）正是我们这一期补的东西（动作资产 + 通道扩充 + 运镜模板）。它选择**交给 Blender**，我们选择**不替代 Blender/Unreal/Maya**（本 change 非目标）——这条差异是刻意的，不是能力缺口 |
| **经验卡片**：从"拉片"提炼镜头用法，命中场景时自动套用（示例：升降的心理语义、J-cut 声音先行 1–2 秒、餐桌戏正反打即权力关系） | 对应我们的**运镜模板**（`cameraMoves.ts`，26 类） | **一条可直接落地的补充**：它的升降经验里有一句我们**没有**的口径——"**升降起止各留 1s 静止**"（让观众先看清再动）。我们现在的升降/摇臂模板是"整段连续运动"，缺首尾停留。已记为 tasks 1.10 |
| **拉片模块**：逐帧解析、灰度图、台词解析、台词认领、镜头语言讲解；把经典影片的**景别 / 运镜 / 时长 / 转场 / 动作 / 台词**解析成结构化数据 | 它做的是**我们入参方向的逆向**：它从成片**抽**结构化镜头，我们从分镜**生成**结构化镜头，中间产物是同一种东西（结构化镜头描述） | 记为**未来输入源**（本次不做）：若把"拉片产物"按我们的 `panels` 结构喂进 `compose_previs_draft`，同一套管线就能服务"**复刻经典镜头**"——目前 `panels` 的字段（`shot_size` / `camera_angle` / `duration_seconds` / `action` / `characters` / `props`）与它的解析产物基本同构 |
| **深度图 + 逐帧解析产物当参考帧** | 与我们**截图回流**（画面 → 分镜）是同一类"图像 → 结构化数据"，方向不同 | 观察项，不行动 |
| **生图成本绕行**：本地 `z-image-turbo` / `qwen3-edit` 质量不足（自述真人/高画质场景不行），云端 Seedream 5.0 Pro **2 天烧掉一个月套餐**（自述），最终把本地 MCP 经 Cloudflare Tunnel 发布到公网、给 ChatGPT 网页版装生图 Skill，**由工作台出提示词、GPT 只当生图工具** | 属**生图线**（另一个 change），与预演台无关 | 对 `7.9 配色 A/B 实测`有参考价值：它佐证了"找免费/廉价后端做对比"的必要性；本地模型名可当候选。**不引入** |
| **母子素材 / 全局引用 / 多状态映射 / 角色专属物品一致性** | 属**资产一致性线**，我们的角色卡 + 参考图 + `match_creative_project_reference_assets` 已在做 | 印证，无新增动作 |

### B. 《用 AI 把任意视频变成 Mixamo 角色动画：Mixamo LLM Mocap》（作者：前端设计大神，2026-09-17）

**它是什么**：开源项目 `squall01337/mixamo-llm-mocap` 的介绍，一条"**锁定相机的视频 → 干净 FK 动画 → 重定向到任意 Mixamo 角色**"的流水线（GVHMR + SMPL-X 姿态估计，Blender MCP 落地，QL 脚本化，逐帧数值 QA）。

**为什么这篇最相关**：它回答的正是 `previs-agent-scene-composition` 里那个被反复问到的"**导入动作还是自己写动作**"。当时我们只在"下载动作库（BVH/Mixamo）"与"手写参数"之间选，结论是"外部动作进不了 `params` 载体，本期自写、骨骼型留后续"。**本文给出了第三条路：视频 → 动作数据**（既不是下载别人的动作库，也不是手写角度）。

| 它的做法 | 对我们的意义 |
| --- | --- |
| **动作即数据**：动作不写死在脚本里，用 `action_spec` JSON 描述（支撑脚时间表含腾空、拳头开合、休息姿态混合…），新增动作只写一个小 JSON | **印证我们的 `carrier=params` 设计**：动作条目就是结构化 JSON（`payload_json` 存逐通道关键帧），新增动作只写数据、不改代码。我们与它在同一个范式上 |
| **"为 AI 代理而设计"**：每个阶段都是 CLI / Socket 调用，关键决策**基于数值而非肉眼观察**，全链路 100% 可脚本化，目标是"让 AI 也能稳定跑通" | **这正是我们本期做的**：`compose_previs_draft` 让 HTTP 接口与 Agent 工具共用一条管线；工具输出为 Agent 精简；拒绝给可读原因；"查不到返回空集而非编造引用"。它是外部同类工程对这套取舍的佐证 |
| **数值化 QA 替代肉眼判断**：把"看起来不对"量化成具体帧区间；`compare_reference.py` 逐帧对比手相对脸的高度、双手间距、肢体穿模、视线方向 | 与我们的**不变量测试**同源：脚底贴地、膝不反折、手不穿躯干、循环首尾相等、走路速度 = 1.3 m/s、运镜首帧等于传入机位、抖动必须确定性。**"数值判据"是本类工程唯一可靠的验收方式**——这一条可写进本 change 的验收依据 |
| **零脚滑靠求解髋部高度 + 支撑脚时间表**（跳跃时整合真实骨盆弧线） | 与我们的做法同类（我们由步幅与步频反推 1.3 m/s，半蹲用"下沉量 + 髋膝屈曲配套"保证脚底贴地）。它的"支撑脚时间表"更通用，是**将来要加跳跃/腾空时的做法参考** |
| **方向保持重定向**：保留估计器的骨骼方向、按目标角色**实测骨骼长度**重算位置 | 若 P2 上骨骼线，"两套骨架朝向不一致"的正解就在这里：**方向不动、只按实测骨长重算位置**——比"推断映射 + 改名 + 重定向"那条老路干净。记入 P2 参考 |
| **双人同框**：按屏幕左右自动拆轨道、按比例差分别重定向、测算分离距离与打击可达范围、Blender 真实网格碰撞 | 我们的预演是"机位与走位可读"，**不需要**接触级正确性；记为了解边界即可 |
| **前置成本与许可（关键红线）** | 需要 **NVIDIA GPU（自述约 8GB 显存）**、**GVHMR 权重约 5GB**、**Blender 5.1+**，且 **SMPL-X 需在官网注册后下载**——**SMPL-X 的许可对商用有限制**，这是能不能用在本项目上的第一道门（与 Mixamo"禁止把动画当独立资产再分发"同一类问题）。**在核实许可之前不引入任何相关依赖** |

### 本节的结论（三条）

1. **不用改方向**：两篇文章从不同侧面印证了我们已经在走的路（分镜 → 结构化操作集 → 3D 预演；动作即数据；数值判据替代肉眼；为 Agent 而设计）。**没有出现"我们走错了"的证据。**
2. **可落地的小改进只有一条**：运镜的**升降起止各留静止**（tasks 1.10）。其余都属"别的线"或"未来才用得上"。
3. **最值得记住的是那条红线**：将来真要做"视频 → 动作"，第一件事是核对 SMPL-X 的商用许可，而不是先装环境。

***

## 调研结论：外部动作数据能否接进我们的动作库（2026-09-20，承接上文 B）

> 调研方法：**核来源本身**（仓库 / 许可页 / 官方条款），不采信公众号转述。上一节里"作者自述"的参数本节重新核过一遍，与转述不符的以本节为准；**仍未核实到的点单独列在最后一节**，不猜。

### 一、结论先行

| 问题 | 答案 |
| --- | --- |
| 文章 B 那条路（GVHMR + SMPL-X）我们能商用吗 | **不能**。SMPL-X 许可页明确禁止商用；GVHMR 自身是非商用学术许可，且**必须联网下载受门控的 SMPL/SMPL-X 体模才能跑** |
| 它的产物能驱动我们的胶囊人吗 | **不能**。产物是**骨骼 FK 动画**（面向 Mixamo 类骨架），落在我们尚未排期的 `carrier=bone` 线上；与 `params`（我们自己的 23 通道）不是同一种东西 |
| 那这件事就完全没路了吗 | **有，但不是文章那条路**：**绕开 SMPL 生态，直接走 `BVH → 我们的 23 通道` 映射器**。数据源可以是免费/条款宽松的 BVH 库，产物是**我们自己的 `params` 条目**，胶囊人立刻能用，且不需要 GPU、不需要 5GB 权重、不需要 SMPL-X |
| 现在做吗 | **不做**。本 change 不需要它（预演只要"看得出在走"，手写 15 条够用），且它不解除任何当前阻塞。建议**另开 change**，见下面的最小切片 |

### 二、核实到的事实（带来源）

| 事实 | 来源 |
| --- | --- |
| 仓库真实存在：`github.com/squall01337/mixamo-llm-mocap`（2026-08 建），自述"视频 → Mixamo 骨架的干净 FK 动画，GVHMR 估计器 + spec 驱动重定向 + Blender MCP 落地" | GitHub 仓库与作者主页（已确认存在，与文章一致） |
| **SMPL-X 许可禁止商用**：许可页原文即"任何其它用途，特别是**商用**、色情、军事或监控用途"均被排除 | `smpl-x.is.tue.mpg.de/modellicense.html`；`vchoutas/smplx` 的 LICENSE 同款表述 |
| **商用只能向 Meshcapade 购买**：Meshcapade 拥有对 SMPL 系列进行再许可的**独家授权** | `meshcapade.com/smpl` |
| **GVHMR 不能脱离 SMPL-X 运行**：其 HuggingFace 卡片给出的用法里有一条 `gvhmr auth smpl`，需要 **MPI 账号**去拉取"受门控的 SMPL/SMPL-X 体模" | HuggingFace `ryanrudes/gvhmr`（GVHMR 权重页） |
| GVHMR 自身许可是**非商用**学术条款（浙江大学 CAD&CG 国家重点实验室版权所有，"为研究目的允许使用/复制/修改/分发"），且 2026-09 还有一次许可相关提交的回退 | PyPI `gvhmr` 的依赖许可信息（non-standard）；`zju3dv/GVHMR` 提交记录 |
| **CMU Motion Capture Database 条款极宽松**，明确**不限制**用途（含商用） | `mocap.cs.cmu.edu`；第三方整理页（deepwiki `una-dinosauria/cmu-mocap` 的许可条目）。**官网 FAQ 建议再逐字核一遍** |
| 另有以 **BVH 格式**发布的大规模动作集：Bandai Namco Research Motiondataset（自述 3000+ 条 / 42 万帧级）、MocapFlow 的免费 FBX/GLB 库 | 上述项目的发布页（**许可未核实**，见末节） |
| 商用 SaaS 成熟且导出格式就是 BVH/FBX：**Rokoko Vision 3.0**（2026-07 起把 **Video-to-Motion 与 Text-to-Motion** 放进同一产品）、DeepMotion、Plask；Rokoko 官方有"motion data inquiry"页且专门区分"商用或非商用" | Rokoko 官方产品页与条款页；DeepMotion / Plask 官方页。**免费档与付费档的商用权限不同，需看条款** |
| **许可干净的开源人体模型是有的**：`naver/anny`（"A Free and Interpretable Human Body Model"，资产源自开源 MakeHuman 框架，PyPI 可装） | `github.com/naver/anny`、NAVER Labs 博客、arXiv 2511.03589。**但"视频→动作"生态几乎全部输出 SMPL-X，Anny 没有对应的前段**——用它等于要自己补一个估计器，工作量陡增 |

### 三、架构判断（本节最重要的一条）

**"视频 → 动作"与"我们现在的动作库"之间隔着的不是格式，是载体。**

```
视频 → (GVHMR/SaaS) → 骨骼 FK 动画（FBX/BVH）
                          ├─ 直接给"带骨骼的模型"用 → 我们尚未排期的 carrier=bone 线
                          └─ 要给胶囊人用 → 必须过一道【重定向到我们 23 通道】的映射
```

- 文章 B 的产出（干净 FK + 重定向到 Mixamo 骨架）解决的是**它的**目标（游戏/影视里驱动带骨骼的角色），**与我们的 `params` 通道之间没有任何现成通路**；
- 但"重定向到我们的 23 通道"这件事**并不可怕**：我们的通道语义在 `humanProxy.tsx` 里是**逐字段写清楚**的（轴序、正方向、镜像规则），且有 82 条数值断言兜底。真正的工作量是"**每个关节对一次轴系**"，而不是"造一套重定向框架"；
- 关键洞察：**做这件事根本不需要 SMPL-X**。需要的是**BVH 这种"骨架 + 每帧关节欧拉角"的朴素格式**，而它是免许可障碍的（CMU 明确免费；SaaS 产出归属条款另说），且**离线一次性**——跑一次、产出一条 `params` 条目、落库，之后完全不依赖外部服务。

### 四、许可红线（按"能不能碰"排序）

| 选项 | 许可状态 | 能否用于本项目 |
| --- | --- | --- |
| SMPL / SMPL-X 体模（→ GVHMR、HMR2.0、WHAM 等一切基于它的估计器） | **禁止商用**；商用须向 Meshcapade 购买 | ❌ 除非付费取得授权 |
| GVHMR 代码本身 | 非商用学术许可 | ❌ |
| CMU Mocap（BVH） | 极宽松、不限制用途（含商用） | ✅ **首选数据源**（官网 FAQ 再核一遍） |
| Bandai Namco / MocapFlow 等 BVH 库 | **未核实** | ⚠️ 先核许可再用 |
| Rokoko Vision / DeepMotion / Plask | 商用需付费档，条款按产品不同 | ⚠️ 若走这条，**先看条款与费用**，并只把它当"离线数据源" |
| Anny（开源人体模型） | 免费、开源（MakeHuman 资产） | ✅ 模型本身没问题；**但它不是"视频→动作"的前段** |
| FreeMoCap（自建多机位无标记动作捕捉） | 开源工具（AGPL 系，仅内部离线使用其产出则不受传染） | ⚠️ 备选：要自己搭多机位、录自己的素材 |

### 五、建议：不做，但把最小切片写清楚（另开 change）

**为什么现在不做**：① 产物落在我们**尚未排期**的骨骼线上，或需要先写映射器；② 预演只需要"看得出在走、站得住、不滑步"，手写动作已经覆盖；③ 引入它不解除任何当前阻塞（本期真正的缺口是"AI 能摆场景"的编排链路，已通）。

**将来要做时的最小切片**（四步，全部可离线、可单测）：

1. **取一条免许可障碍的 BVH**（CMU 库里挑一段"走"或"挥"）；
2. **写映射器**：BVH 关节欧拉角 → 我们的 23 通道（`torso` / `head` / 肩肘髋膝 / `bodyOffsetY`），逐关节对轴系；髋部位移按 BVH 的根位移换算成我们"步幅 × 步频"的位移口径；
3. **用既有不变量验收**（这是本类工作唯一可靠的验收方式）：脚底贴地、膝不反折、肘不反折、循环首尾相等、速度与步幅自洽、无穿模；
4. **落库成 `params` 条目**（`origin` 记来源、`license` 记 CMU/CC 条款链接、`license_status` 如实），胶囊人立刻能选它。

**四步里最值钱的是第 2 步**：映射器一旦成立，"**任何** BVH（含将来 Rokoko/自录）都能一键进我们的动作库"，这才是把"导入动作"这件事一次性解决；而文章 B 那条路（GVHMR + SMPL-X + Blender MCP）除了许可不通，还把我们绑在一个 5GB 权重 + 8GB 显存的运行时依赖上——与"预演台要轻、要能随时跑"是冲突的。

### 六、未核实 / 存疑（不猜，标记待查）

- **CMU 官网 FAQ 的逐字表述**（第三方整理页称"不限制用途"，未从官网原文确认）；
- **Bandai Namco Research Motiondataset 与 MocapFlow 免费库的实际许可**（是否允许商用、是否要求署名）；
- **Rokoko Vision 免费档与付费档的商用权限差异**（官方有专门的商用询问页，说明确实分档）；
- **SMPL-X 的"模型"与"用该模型估出的动作数据"是否可按不同条款使用**——这是个法律灰区，**不作为方案的依据**（宁可选一条不需要它的路）。
4. **不做的事**：不引入其源码、不下载其素材、不因此恢复已下线的 UE 白模（人形占位仍只有程序化胶囊人）。

***

## 内容生产与去水印参考（另一条线落地）

### libtv — 短剧生产平台

内容生产方案（`production_profile`）与导演 Agent 编排的交互参考：阶段化生产流程、平台适配、多角色导演编排。仅借鉴产品形态与工作流，不复制实现。

### guillaumemeyer/watermarks-remover

**GitHub**: <https://github.com/guillaumemeyer/watermarks-remover>\
**许可**: MIT（v0.5.0，本地服务边界见 `docs/reference/watermarks-remover.md`）

AI 水印/元数据去除的开源参考。YLCraft 采用内部适配器 `remove-ai-marks` + `asset_provenance` 服务，借鉴其"扫描 → 预览 → 生成清理副本 → 回滚"交互，不依赖其推理模型；清理动作非破坏式（原文件不覆盖，派生资产 `derived_from` 回指）。
