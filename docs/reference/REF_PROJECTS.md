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
| `frontend/public/models/ue-mannequin.glb` | Sketchfab（作者 William Luque，经 storyai 仓库） | Sketchfab Standard | 可商用、保留署名、不得单独打包转售/再分发；许可见 `frontend/public/models/LICENSE-UE-MANNEQUIN.txt` |
| `frontend/public/models/vanguard.glb` | open-storyboard-canvas（MIT 二开 Storyboard-Copilot） | MIT | 可自由使用，保留上游署名（henjicc）；许可见 `frontend/public/models/LICENSE-VANGUARD.txt` |
| 胶囊人（程序化） | storyai ProceduralMannequin 思路自写 | 无外部依赖 | 可摆姿势，无版权风险 |
