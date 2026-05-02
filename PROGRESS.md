# YLCraft — 开发进度

> 最后更新：2026-04-29
> 设计文档：`DESIGN.md`

---

## 当前状态总览

```
[█████████████████████████████████████████████░]  ~97%
```

| 模块 | 状态 | 说明 |
|------|------|------|
| 需求分析 | ✅ 完成 | 12 个开源项目源码分析 |
| 系统设计 | ✅ 完成 | 完整架构设计文档 |
| BackendManager | ✅ 完成 | Protocol + Registry + YAML + Manager |
| Backend 实现 | ✅ 完成 | 7 个 Backend |
| API 层 | ✅ 完成 | Provider/LLM/Images/TTS/Breaker/Story/Videos 端点 |
| CutClaw 模式 | ✅ 完成 | Agent 工具调用 + FFmpeg 渲染 |
| NarratoAI 模式 | ✅ 完成 | Pipeline 流水线（纪录片/短剧）|
| MoE 多专家 | ✅ 完成 | 三专家 + ControlPlane 编排器 |
| 爆款拆解 | ✅ 完成 | Breaker API + 内置视频解析（yt-dlp）|
| Story Maker | ✅ 完成 | 角色库 + 分镜 Agent + 一致性检查 + 9 个 API 端点 |
| OpenClaw Skill | ✅ 完成 | 10 个 Skill 脚本（breaker/clip/story/llm/image/tts）|
| **AI 图像生成** | ✅ 完成 | ImageBackend + MiniMax Provider + 前端页面 |
| **AI 视频生成** | ✅ 完成 | VideoBackend + MiniMax Provider + 前端页面 + 轮询 |
| 前端 Phase 1 | ✅ 完成 | 6 个页面 + 路由 + API Client |
| 前端 Phase 2（素材库） | ✅ 完成 | 素材库 Grid + 搜索 + 标签 + 详情抽屉 + 引用机制 |
| 前端 Phase 3（后台下载） | ✅ 完成 | 后台任务队列 + 轮询进度，解决大文件 XHR 超时 |
| 前端 Phase 4（角色管理） | ✅ 完成 | 角色 CRUD + 来源标签 + 定位 + 收藏/冻结 |
| 前端 Phase 5（AI 生成） | ✅ 完成 | 图像生成 + 视频生成页面 + 深色主题 |
| 前端 Phase 6（任务管理） | ✅ 完成 | 任务列表 + 过滤搜索 + 自动刷新 + 操作 |
| Live 2D 工厂 | 🚧 开发中 | 立绘生成 + 图层拆分 + 身体绑骨(✅) + 五官绑骨(🚧) + cmo3→moc3(✅) |

---

## 已完成 ✅

### 需求分析
- [x] **ArcReel 源码分析** — Protocol + Dataclass + Registry 架构
- [x] **Jellyfish 源码分析** — Provider 注册表 + LangChain Agent
- [x] **MoneyPrinterTurbo 分析** — YAML 配置 + if-else 分发
- [x] **CutClaw 源码分析** — LLM Agent Tool Calling 剪辑
- [x] **NarratoAI 源码分析** — Pipeline 流水线 + Provider 双模式
- [x] **montage-ai 源码分析** — MoE 多专家协作架构
- [x] **seedance2 SDK 分析** — MiniMax 图像/视频生成 SDK

### 系统设计
- [x] **DESIGN.md 完成** — 完整设计文档，涵盖：
  - 系统架构（BackendManager / Agent / Provider）
  - BackendManager 核心实现（Protocol + Registry + YAML）
  - Clip Lab 三大模式（CutClaw / NarratoAI / MoE）
  - 爆款拆解服务设计
  - OpenClaw Skill 设计
  - **AI 图像/视频生成架构**（第十一章）
  - 技术选型

### AI 生成模块（2026-04-29 新增）
- [x] **核心类型定义** — `core/contracts/types.py`
  - ImageGenerationRequest / ImageGenerationResult
  - VideoGenerationRequest / VideoGenerationResult
  - ImageBackend / VideoBackend Protocol
  - poll_with_retry / download_file 工具函数
- [x] **Image Backend**
  - `services/image/base.py` — BaseImageBackend 抽象基类
  - `services/image/minimax.py` — MiniMax/Seedance 图像生成
- [x] **Video Backend**
  - `services/video_gen/base.py` — BaseVideoBackend 抽象基类
  - `services/video_gen/minimax.py` — MiniMax/Seedance 视频生成
- [x] **BackendManager 重构** — 真正实例化 Backend，支持自动降级
- [x] **API 端点**
  - `POST /api/v1/images/generate` — 图像生成
  - `GET /api/v1/images/backends` — 可用后端列表
  - `POST /api/v1/videos/generate` — 视频生成
  - `GET /api/v1/videos/backends` — 可用后端列表
  - `GET /api/v1/videos/tasks/{task_id}` — 任务状态轮询
- [x] **配置更新** — `providers.yaml` 新增 video provider

### 前端（任务管理页面，2026-05-02 新增）
- [x] **任务管理页面重写** — `/tasks`
  - 接入真实 API（listTasks/getTask/cancelTask/deleteTask）
  - 任务类型过滤（爆款拆解/下载/图像生成/视频生成/剪辑）
  - 搜索框（任务ID/消息）
  - 自动刷新（30秒间隔）
  - 任务操作：查看详情、取消、删除
  - 状态图标闪烁动画（运行中的任务）
- [x] **TypeScript 错误修复**
  - GeneratedVideo 接口添加缺失属性（aspect_ratio/resolution）
  - AppLayout 菜单类型修复（移除无效 type: 'group'）

### 前端（AI 生成页面，2026-04-29 新增）
- [x] **图像生成页面** — `/image-gen`
  - 文生图 / 图生图 切换
  - 提示词 + 反向提示词输入
  - 参考图片上传（图生图）
  - Provider / 尺寸 / 批量数量 / 种子 参数配置
  - 生成结果网格展示
  - 下载 / 复制提示词 / 删除 操作
- [x] **视频生成页面** — `/video-gen`
  - 文生视频 / 图生视频 切换
  - 首帧图片上传（图生视频）
  - Provider / 分辨率 / 画幅 / 时长 参数配置
  - 任务提交 → 轮询状态（5秒间隔）
  - 任务队列 Timeline 展示
  - 视频预览弹窗
  - 统计面板
- [x] **Dashboard 更新** — 6 大功能入口卡片 + 统计面板
- [x] **侧边栏重构** — 分组菜单 + 深色主题
- [x] **全局样式** — 深色科技风主题（`index.css`）

---

## 决策记录 📋

### 决策 1：模型抽象层方案
**问题**：如何设计可替换的模型调用层？
**选择**：融合 ArcReel（Protocol + Dataclass）+ Jellyfish（Provider 注册表）+ MoneyPrinterTurbo（YAML 配置）
**原因**：ArcReel 最完整，但 Jellyfish 的注册表有别名解析和线程安全优势，MoneyPrinterTurbo 的 YAML 配置最简单易用
**日期**：2026-04-15

### 决策 2：剪辑工具架构
**问题**：Clip Lab 采用哪种 AI 剪辑方案？
**选择**：三种模式并存：CutClaw（Agent 驱动）+ NarratoAI（Pipeline）+ MoE（多专家）
**原因**：不同场景适合不同方案，CutClaw 适合智能判断，NarratoAI 适合固定流程，MoE 适合精细控制
**日期**：2026-04-15

### 决策 3：OpenClaw 集成方式
**问题**：如何让 AI Agent 调用平台能力？
**选择**：Skill 封装 REST API，Skill 脚本通过 HTTP 调用后端
**原因**：Skill 是 OpenClaw 的标准扩展方式，且不侵入后端代码
**日期**：2026-04-15

### 决策 4：资产库（素材库）架构
**问题**：资产管理的层次结构如何设计？
**选择**：
- 底层：统一资产库（Asset Library），支持多种资产类型（视频/图片/音频/角色/商品/场景/道具）
- 角色作为资产的一种类型（CHARACTER），与视频/图片并列
- 素材库页面 → 资产库（改名）
- 角色管理页面暂时保留，未来可整合进资产库的"角色" Tab
**原因**：
  - 角色是 Story Maker 的核心，但也是其他场景（电商/摄影）共用的元素
  - 统一资产库避免数据分散，引用机制更简单
  - 电商/摄影/短剧的区别在于"场景"和"用途"，不在于资产本身
**日期**：2026-04-19

### 决策 5：功能维度 vs 用户场景维度
**问题**：功能模块按什么维度组织？
**选择**：以功能模块为维度组织，用户场景（电商/摄影/短剧）作为标签/分类属性
**原因**：
  - 爆款拆解 → 电商/摄影/短剧 都用
  - 视频剪辑 → 电商/摄影/短剧 都用
  - AI 生成 → 所有场景共用
  - 素材库 → 所有场景共用
**日期**：2026-04-19

### 决策 6：AI 生成 Provider 架构（2026-04-29 新增）
**问题**：如何统一调度多种 AI 生成服务？
**选择**：参考 ArcReel 的 Backend 架构
  - Protocol 定义接口（ImageBackend / VideoBackend）
  - dataclass 定义 Request/Result
  - Registry 注册工厂
  - BackendManager 从 YAML 加载配置并实例化 Backend
**原因**：
  - ArcReel 的架构最完整，已在生产环境验证
  - Protocol 接口支持静态类型检查
  - Registry 支持动态注册新 Provider
  - YAML 配置易于修改，无需改代码
**日期**：2026-04-29

---

## 技术债务 🏚️

- [ ] FFmpeg 环境依赖未验证（Windows 兼容性）
- [ ] Madmom 在 Windows 上的安装问题
- [ ] CogVideoX 本地部署指南缺失
- [ ] Provider API Key 安全存储（目前明文/环境变量）
- [x] 图像/视频生成结果入库到 Asset 表 ✅ 已实现（asset_service.py）
- [ ] FFmpeg 视频剪辑服务完善
- [ ] WebSocket 替代轮询（实时推送任务进度）
- [x] 后台下载任务 ✅ 已实现（BackgroundTasks + 内存任务表 + 轮询）
- [x] 前端移动端适配 ✅ 完成（Drawer 侧栏 + 响应式栅格 + 移动端工具类）
- [x] 代码分割优化 ✅ 完成（manualChunks，antd 641KB gzip 177KB）

---

## 下一步行动 →

**当前状态**：Phase 1-6 前后端核心功能全部完成，整体进度 ~97%

### 待完成 ⏳
1. [ ] 测试 AI 生成 API（需要配置 MiniMax API Key）
2. [x] WebSocket 实时进度推送 ✅ 完成
3. [ ] Live 2D 工厂五官绑骨完善

### 可以开始的工作 ✅
- 启动后端服务测试所有 API
- 启动前端开发服务器验证 UI
- 配置 API Key 测试 AI 生成功能

---

## Live 2D 工厂进度

> **适用人群**：COSER
> **最后更新**：2026-04-28

### 状态总览

```
[████████████░░░░░░░]  ~70%
```

| 环节 | 状态 | 技术方案 |
|------|------|---------|
| 立绘生成 | ✅ 完成 | image2 |
| 图层拆分 | ✅ 完成 | seethrough 改进窗口批量版 |
| 身体绑骨 | ✅ 完成 | stretchystudio 改进版 + py 插件 vts 兼容转化 |
| 五官绑骨 | 🚧 开发中 | 基于 stretchystudio 二次开发，实现五官运动 |
| cmo3→moc3 转化 | ✅ 自研完成 | cmo3 转化为 vts 通用模型格式 |

---
