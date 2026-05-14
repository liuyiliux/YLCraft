# YLCraft — 开发进度

> 最后更新：2026-05-14
> 设计文档：`DESIGN.md`

---

## 当前状态总览

```
[███████████████████████████████████████████████]  ~100%
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
| **Live 2D 工厂** | ✅ 完成 | 立绘生成 + 图层拆分 + 绑骨 + VTS导出 + 口型同步 + 批量处理 |
| **字幕提取** | ✅ 完成 | faster-whisper medium + 4 种样式 + SRT/ASS/VTT + 烧录 |
| **BGM 配乐** | ✅ 完成 | 10 首内置曲目 + 用户上传 + FFmpeg 混音 + 淡入淡出 |
| **素材采集** | ✅ 完成 | MediaCrawler 集成 + 多平台搜索 + 导入素材库 |
| **小说阅读** | ✅ 完成 | 书架 + 阅读器 + 书源管理 + 换源 + SSE 流式搜索 |
| **账号矩阵** | ✅ 完成 | 统一凭证 + Drawer + Segmented + 健康检查（参考 XHS_ALL_IN_ONE）|

---

## 设计文档索引

| 文档 | 说明 | 状态 |
|------|------|------|
| `DESIGN.md` | 主设计文档（架构圣经） | ✅ 已完成 |
| `agent-platform-design.md` | Agent 通用平台设计（参考 OpenClaw/Hermes） | ✅ 已实现 |
| `architecture-image-video-backends-v2.md` | 图像/视频生成后端架构 v2（Generic + ComfyUI） | 📋 设计阶段 |
| `comfyui-pixelle-evolution-design.md` | ComfyUI 集成方案（参考 Pixelle-Video） | 📋 设计阶段 |
| `COMFYUI_DIGITAL_HUMAN_ANALYSIS.md` | ComfyUI 数字人分析 | 📋 分析完成 |
| `xhs-parser-design.md` | 小红书图文链接解析器 | ✅ 已实现 |
| `live2d-factory-design.md` | Live2D 工厂设计 | ✅ 已实现 |
| `live2d-processing-mode-design.md` | Live2D 处理模式设计 | ✅ 已实现 |
| `story-maker-design.md` | Story Maker 设计 | ✅ 已实现 |
| `cookie-acquisition-design.md` | Cookie 自动获取设计 v2.0（统一凭证 + Playwright + QrCode） | ✅ 前端已实现，后端部分实现 |
| `REF_PROJECTS.md` | 参考项目列表 | 📋 参考文档 |

---

## 2026-05-14 更新

### 账号矩阵页面重构（参考 XHS_ALL_IN_ONE）✅

参考 [XHS_ALL_IN_ONE](https://github.com/cv-cat/XHS_ALL_IN_ONE) 项目，对平台管理页面进行了全面重构：

**架构层面改进**：

| 改进点 | 原设计 | 新设计（参考 XHS_ALL_IN_ONE） |
|--------|--------|------|
| 页面标题 | 「平台连接器」 | 「账号矩阵」— 体现多账号管理理念 |
| 添加账号 | 3 个独立 Modal | **1 个 Drawer 抽屉** — 更沉浸，空间更大 |
| 登录方式切换 | Dropdown | **Segmented 分段控件** — Cookie/扫码/浏览器，更直观 |
| 健康检查 | 全局测试按钮 | **每个卡片独立「检查」按钮** — 参考账号矩阵巡检 |

**新增组件**：

| 组件 | 说明 |
|------|------|
| `AddAccountDrawer` | 添加账号抽屉（Segmented 方式切换） |
| `CookieImportPanel` | Cookie 手动导入面板 |
| `QrLoginPanel` | 二维码登录面板（自包含 WebSocket） |
| `BrowserLoginPanel` | 浏览器登录面板（自包含 WebSocket） |
| `ApiKeyPanel` | API Key 导入面板 |
| `ConnectionCard` | 连接卡片（Avatar + 状态 Tag + 健康检查） |
| `PlatformGroupCard` | 平台分组卡片 |
| `StatusTag` | 状态标签组件 |

**Cookie 自动获取后端实现**：

| 文件 | 说明 | 大小 |
|------|------|------|
| `services/cookie_acquisition/base.py` | 抽象基类 | 8.6KB |
| `services/cookie_acquisition/playwright_manager.py` | Playwright 会话管理 | 15.9KB |
| `services/cookie_acquisition/qrcode_manager.py` | QrCode 会话管理 | 12.6KB |
| `services/cookie_acquisition/platforms/` | 6 个平台适配器 | — |
| `api/v1/cookie_acquisition.py` | Cookie 获取 API | 11.4KB |

---

## 2026-05-07 更新

### AI 连接器 API 修复 ✅

**问题描述**：
- AI 连接器 API 返回 500 内部服务器错误
- 前端设置页面无法加载 AI 连接器列表

**根本原因**：
1. **异步/同步混乱** — 错误地将异步代码改成了同步
2. **语法错误** — `service.py` 第 16 行 import 语句未正确关闭括号
3. **缺失依赖** — `jinja2` 和 `jsonpath_ng` 模块未安装

**修复方案**：

#### 1. 恢复异步支持 (`service.py`)
- 将 `Session` 改为 `AsyncSession`
- 所有方法改为 `async def`：
  - `list_all`, `list_by_provider`, `list_active`
  - `get`, `get_default`, `get_by_provider`
  - `create`, `update`, `delete`
  - `test_connection`, `log_usage`, `get_usage_stats`
  - `_clear_default`
- 所有数据库操作添加 `await`：
  - `await self.session.execute()`
  - `await self.session.commit()`
  - `await self.session.refresh()`
  - `await self.session.get()`

#### 2. 修复路由 (`ai_connectors.py`)
- Router prefix 设为 `/connectors`
- 使用异步依赖 `get_ai_service()` (基于 `AsyncSessionLocal`)
- 所有路由都是 `async def`
- 所有 service 方法调用都加了 `await`
- 修复路径（如 `/` 而不是 `/connectors/`）

#### 3. 安装缺失依赖
```bash
pip install jinja2 jsonpath-ng
```

**验证结果**：
- ✅ AI 连接器路由器成功加载（无警告）
- ✅ 后端服务器启动成功
- ✅ 4 个 LLM Provider 成功注册（openai/gpt-5.2, 硅基流动-*）
- ✅ 4 个 Image Provider 成功注册
- ✅ 9 个社交媒体连接器加载成功
- ✅ 1 个 AI 连接器加载成功

**关键文件**：
- `F:\PycharmProjects\YLCraft\backend\app\api\v1\ai_connectors.py`
- `F:\PycharmProjects\YLCraft\backend\app\services\ai_connector\service.py`
- `F:\PycharmProjects\YLCraft\backend\app\db\database.py`

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

### 决策 7：账号矩阵 UI 架构（2026-05-14 新增）
**问题**：平台管理页面如何设计多账号管理体验？
**选择**：参考 XHS_ALL_IN_ONE 项目的设计
  - 页面标题改为「账号矩阵」
  - 从 3 个独立 Modal 改为 1 个 Drawer 抽屉 + Segmented 分段控件
  - 每个连接卡片增加独立「健康检查」按钮
  - Cookie/扫码/浏览器三种方式用分段控件切换
**原因**：
  - XHS_ALL_IN_ONE 的 Drawer + Segmented 比多 Modal 更沉浸、更直观
  - 账号矩阵概念更契合多账号管理场景
  - 独立健康检查按钮参考了 Cookie 过期巡检的成熟实践
**日期**：2026-05-14

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
- [ ] CookieManager 适配（从 PlatformConnection 读 Cookie）

---

## 下一步行动 →

**当前状态**：Phase 1-6 前后端核心功能全部完成，整体进度 ~98%

### 待完成 ⏳
1. [ ] 测试 AI 生成 API（需要配置 MiniMax API Key）
2. [x] WebSocket 实时进度推送 ✅ 完成
3. [ ] Live 2D 工厂五官绑骨完善
4. [ ] CookieManager 适配（从 PlatformConnection 读 Cookie）

### 可以开始的工作 ✅
- 启动后端服务测试所有 API
- 启动前端开发服务器验证 UI
- 配置 API Key 测试 AI 生成功能
- 测试账号矩阵页面（Drawer + 扫码 + 浏览器获取）

---

## Live 2D 工厂进度

> **适用人群**：COSER
> **最后更新**：2026-05-04 23:38

### 状态总览

```
[█████████████████████████████████████████████░]  ~98%
```

| 环节 | 状态 | 技术方案 |
|------|------|---------|
| 立绘生成 | ✅ 完成 | image2 |
| 图层拆分 | ✅ 完成 | seethrough 改进窗口批量版 |
| 身体绑骨 | ✅ 完成 | stretchystudio 改进版 + py 插件 vts 兼容转化 |
| 五官绑骨 | ✅ 完成 | Python 实现面部关键点检测 + 骨骼绑定 |
| cmo3→moc3 转化 | ✅ 自研完成 | cmo3 转化为 vts 通用模型格式 |
| 待机动作 | ✅ 完成 | 眨眼 + 呼吸 + 视线移动动画 |
| 表情切换 | ✅ 完成 | 7 种预设表情（neutral/happy/sad/angry/surprised/loved/focused）|
| 视线跟随 | ✅ 完成 | 平滑插值控制眼球运动 |
| 前端实时预览 | ✅ 完成 | 预览弹窗 + 表情控制 + 视线跟踪 + 骨骼数据展示 |
| **WebSocket 实时进度** | ✅ 完成 | WebSocket 推送处理进度，实时更新 UI |
| **一键生成流水线** | ✅ 完成 | 自动执行：抠图→风格转换→分层→绑骨→动作→导出 |
| **处理中断恢复** | ✅ 完成 | 支持中断和恢复流水线 |
| **WebGL 实时预览** | ✅ 完成 | Live2DViewer 组件 + Canvas 2D 渲染 |
| **VTS 格式导出** | ✅ 完成 | vts_exporter.py 服务，导出 .model3.json |
| **口型同步** | ✅ 完成 | lip_sync.py 服务，基于音频幅度分析 |
| **角色库联动** | ✅ 完成 | /characters 端点 + 关联/创建模型 |
| **动作预设库** | ✅ 完成 | motion_presets.py，16 种预设动作 |
| **批量处理队列** | ✅ 完成 | batch_queue.py，支持多任务排队和优先级 |

### 实现细节（2026-05-04 更新）

#### 服务层文件
- [x] `services/live2d/rembg.py` - AI 抠图服务 (RMBG-1.4)
- [x] `services/live2d/style_transfer.py` - 风格转换服务 (AnimeGAN)
- [x] `services/live2d/segmentation.py` - AI 自动分层服务
- [x] `services/live2d/rigging.py` - 五官绑骨服务
- [x] `services/live2d/vts_exporter.py` - VTS 格式导出服务
- [x] `services/live2d/lip_sync.py` - 口型同步服务
- [x] `services/live2d/motion_presets.py` - 动作预设库（16 种预设）
- [x] `services/live2d/batch_queue.py` - 批量处理队列管理器

#### API 端点（2715 行）
- [x] `POST /live2d/{model_id}/rembg` - AI 抠图
- [x] `POST /live2d/{model_id}/style-transfer` - 风格转换
- [x] `POST /live2d/{model_id}/segment` - 自动分层
- [x] `POST /live2d/{model_id}/rig` - 面部绑骨
- [x] `GET /live2d/{model_id}/rigging/state` - 获取绑骨状态
- [x] `PUT /live2d/{model_id}/rigging/expression` - 更新表情
- [x] `PUT /live2d/{model_id}/rigging/eye-tracking` - 更新视线跟踪
- [x] `POST /live2d/{model_id}/motion` - 生成待机动作
- [x] `POST /live2d/{model_id}/export` - 导出 VTS 格式
- [x] `POST /live2d/{model_id}/lip-sync` - 生成口型同步
- [x] `GET /live2d/characters` - 获取角色库列表
- [x] `GET /live2d/{model_id}/character` - 获取模型关联角色
- [x] `POST /live2d/{model_id}/link-character` - 关联角色
- [x] `POST /live2d/from-character/{id}` - 从角色创建模型
- [x] `POST /live2d/batch` - 创建批量处理队列
- [x] `GET /live2d/batch` - 获取所有队列
- [x] `GET /live2d/batch/{id}` - 获取队列详情
- [x] `POST /live2d/batch/{id}/start` - 启动队列处理
- [x] `POST /live2d/batch/{id}/cancel` - 取消队列

#### 前端组件
- [x] `pages/live2d/` - Live2D 工厂页面
- [x] `components/live2d/Live2DViewer.tsx` - Canvas 2D 实时预览组件

#### 数据库初始化
- [x] `api_keys` 表创建成功
- [x] `live2d_models` / `live2d_bones` / `live2d_motions` 表已存在

---

## 素材采集模块（2026-05-05 新增）

> 集成 MediaCrawler 核心功能，支持多平台视频/图文素材搜索与采集

### 后端新增文件
- `backend/app/services/crawler/__init__.py` — 模块导出
- `backend/app/services/crawler/service.py` — CrawlerService（搜索 + 导入素材库 + 降级方案）
- `backend/app/api/v1/crawler.py` — 素材采集 API（platforms/options/search/import/tasks）

### 后端修改文件
- `backend/app/main.py` — 注册 crawler 路由

### 前端新增文件
- `frontend/src/pages/crawler/index.tsx` — 素材采集页面（平台选择 + 关键词搜索 + 结果表格 + 导入素材库）

### 前端修改文件
- `frontend/src/App.tsx` — 新增 /crawler 路由
- `frontend/src/components/layout/AppLayout.tsx` — 新增「素材采集」菜单项
- `frontend/src/api/index.ts` — 新增 crawler API 函数（~25 行）

### 支持平台
| 平台 | 标识 | 颜色 |
|------|------|------|
| 小红书 | xhs | #fe2c55 |
| 抖音 | dy | #000000 |
| 快手 | ks | #ff5000 |
| B站 | bili | #00aeec |
| 微博 | wb | #ff8200 |
| 知乎 | zhihu | #0066ff |

### API 端点
- `GET /api/v1/crawler/platforms` — 获取支持的平台列表
- `GET /api/v1/crawler/options` — 获取配置选项
- `POST /api/v1/crawler/search` — 搜索视频/图文素材
- `POST /api/v1/crawler/import` — 将采集结果导入素材库
- `GET /api/v1/crawler/tasks/{id}` — 查询采集任务状态

### 技术要点
- 优先使用 MediaCrawler（Playwright 浏览器自动化），失败则降级到 yt-dlp 搜索
- 采集结果可批量导入 YLCraft 素材库
- 支持按平台筛选、关键词搜索、分页展示
- 参考项目：https://github.com/NanmiCoder/MediaCrawler

---

## AI 生成配置文档（2026-05-08 新增）

> 详细配置指南见 `AI_GENERATION_CONFIG.md`

### 设计文档索引更新
| 文档 | 说明 | 状态 |
|------|------|------|
| `AI_GENERATION_CONFIG.md` | AI 生成配置指南（图像/视频） | ✅ 新增 |

### 架构分析

| 类型 | Backend 类 | 配置方式 | 说明 |
|------|-----------|---------|------|
| LLM | `GenericLLMBackend` | 数据库 | ✅ 完全可配置 |
| 图像 | `GenericImageBackend` | 数据库 | ✅ 完全可配置（支持 request_template + response_config）|
| 视频 | `MinimaxVideoBackend` | 硬编码 | ⚠️ 需要创建 GenericVideoBackend |
| TTS | 占位实现 | - | ❌ 未实现 |

### 关键发现

1. **图像生成**：使用 `GenericImageBackend`，配置存储在数据库
   - 需要在 `ai_connectors` 表插入 `provider_type = 'image'` 的记录
   - `request_template` 使用 Jinja2 语法
   - `response_config` 使用 JSONPath 解析响应

2. **视频生成**：使用硬编码的 `MinimaxVideoBackend`
   - 配置灵活性低，不支持数据库配置模板
   - 建议后续创建 `GenericVideoBackend`

3. **图生图**：通过 `reference_images` 参数实现
   - Provider 需要设置 `support_reference_image = True`
   - `request_template` 需要包含 `{{ reference_images[0] }}` 占位符

### 待改进项
- [ ] 创建 `GenericVideoBackend`，支持数据库配置模板
- [ ] 实现 `GenericTTSBackend`
- [ ] 前端设置页面根据 `provider_type` 显示不同配置表单

---

## 小说阅读模块（2026-05-14 新增）

> 集成小说阅读功能，支持多书源管理和在线阅读

### 后端服务文件
- `backend/app/services/novel/book_source_manager.py` — 书源管理器（批量操作 + 搜索并发）
- `backend/app/services/novel/downloader.py` — 章节下载器
- `backend/app/services/novel/crawler.py` — 小说爬虫服务
- `backend/app/api/v1/novels.py` — 小说 API 路由

### 数据模型
- `backend/app/db/models/novel.py` — `NovelChapter` 章节表

### 前端页面
- `frontend/src/pages/novel-bookshelf/` — 书架页面
- `frontend/src/pages/novel-reader/` — 阅读器页面
- `frontend/src/pages/novel-search/` — 小说搜索页面

### 支持功能
| 功能 | 说明 |
|------|------|
| 多书源管理 | 批量添加/编辑/启用书源，支持 Legado JS 模板 |
| 书源搜索 | 多源并发搜索，SSE 流式响应 |
| 章节目录 | 自动获取并缓存章节列表 |
| 在线阅读 | 支持换源，记住阅读进度 |
| 本地下载 | 章节内容下载到本地 |

### API 端点
- `GET /api/v1/novels/sources` — 获取书源列表
- `POST /api/v1/novels/sources` — 添加书源
- `PUT /api/v1/novels/sources/{id}` — 更新书源
- `DELETE /api/v1/novels/sources/{id}` — 删除书源
- `GET /api/v1/novels/search` — 搜索小说（SSE 流式）
- `GET /api/v1/novels/{id}/chapters` — 获取章节列表
- `GET /api/v1/novels/chapters/{id}/content` — 获取章节内容

---

## Agent 平台（2026-05-14 确认）

> Agent 通用平台设计已实现，参考 `agent-platform-design.md`

### 已实现功能
- `backend/app/services/agent/service.py` — Agent 核心服务
- `backend/app/services/agent/registry.py` — 工具注册表
- `backend/app/services/agent/memory/` — 记忆管理器
- `backend/app/services/agent/session/` — 会话管理器
- `backend/app/services/agent/tools/` — 工具集
- `backend/app/api/v1/agent.py` — Agent API 路由
- `frontend/src/pages/agent/` — Agent 前端页面

---

## Cookie 自动获取模块（2026-05-14 新增，2026-05-14 更新）

> 集成 Playwright 浏览器自动化 + 二维码扫码，自动获取自媒体平台 Cookie
> 详细设计见 `cookie-acquisition-design.md`
> **v2.0 重构：统一凭证架构，废弃 PlatformCookie + SocialMediaConnector，统一为 PlatformConnection**
> **参考项目：XHS_ALL_IN_ONE（账号矩阵 UI + Drawer 抽屉 + Segmented 方式切换）**

### 状态总览

```
[████████████████████████████████████░░░░░░░░░]  ~75%
```

| 功能 | 状态 | 说明 |
|------|------|------|
| PlatformConnection 模型增强 | ✅ 完成 | acquisition_method / cookie_content / account_* / domains 字段已定义 |
| 数据迁移 | ✅ 完成 | PlatformCookie + SocialMediaConnector → PlatformConnection 迁移脚本已创建 |
| 废弃旧 API/服务 | ✅ 完成 | cookies.py + social_media.py + 旧模型已删除 |
| CookieManager 适配 | ⏳ 待开始 | 从 PlatformConnection 读 Cookie |
| 抽象基类 | ✅ 完成 | `BaseAcquirer` / `AcquisitionResult` / `AcquisitionStatus` |
| Playwright 管理器 | ✅ 完成 | `PlaywrightAcquisitionManager` — 浏览器会话管理 + Cookie 提取 |
| QrCode 管理器 | ✅ 完成 | `QrcodeAcquisitionManager` — 二维码生成 + 状态轮询 |
| 平台适配器（6个） | ✅ 完成 | 小红书/抖音/快手/B站/微博/知乎 6 个平台适配器 |
| API 端点 | ✅ 完成 | Playwright start/ws/cancel/sessions + QrCode generate/ws/status/refresh |
| WebSocket 推送 | ✅ 完成 | 实时状态推送（status_update / completed / error） |
| 前端页面 | ✅ 完成 | 账号矩阵页面重构（Drawer + Segmented + 健康检查） |

### 后端服务文件

- `backend/app/services/cookie_acquisition/__init__.py` — 模块导出
- `backend/app/services/cookie_acquisition/base.py` — 抽象基类 AcquisitionResult / BaseAcquirer / AcquisitionStatus
- `backend/app/services/cookie_acquisition/playwright_manager.py` — Playwright 会话管理器（15.9KB）
- `backend/app/services/cookie_acquisition/qrcode_manager.py` — QrCode 会话管理器（12.6KB）
- `backend/app/services/cookie_acquisition/platforms/__init__.py` — 平台适配器注册
- `backend/app/services/cookie_acquisition/platforms/xiaohongshu.py` — 小红书适配
- `backend/app/services/cookie_acquisition/platforms/douyin.py` — 抖音适配
- `backend/app/services/cookie_acquisition/platforms/kuaishou.py` — 快手适配
- `backend/app/services/cookie_acquisition/platforms/bilibili.py` — B站适配
- `backend/app/services/cookie_acquisition/platforms/weibo.py` — 微博适配
- `backend/app/services/cookie_acquisition/platforms/zhihu.py` — 知乎适配

### 后端 API 端点

```
Playwright:
  POST  /api/v1/acquire/playwright/start          — 启动浏览器会话
  WS    /api/v1/acquire/playwright/{sid}/ws       — WebSocket 状态推送
  POST  /api/v1/acquire/playwright/{sid}/cancel   — 取消会话
  GET   /api/v1/acquire/playwright/sessions        — 列出活跃会话

QrCode:
  POST  /api/v1/acquire/qrcode/generate           — 生成登录二维码
  WS    /api/v1/acquire/qrcode/{sid}/ws            — WebSocket 等待扫码结果
  GET   /api/v1/acquire/qrcode/{sid}/status        — 轮询扫码状态
  POST  /api/v1/acquire/qrcode/{sid}/refresh       — 刷新过期二维码

Cookie Content:
  GET   /api/v1/platforms/{id}/cookie-content       — 获取连接的 Cookie 内容
  POST  /api/v1/platforms/{id}/cookie-content       — 保存连接的 Cookie 内容
```

### 前端页面（账号矩阵 — 参考 XHS_ALL_IN_ONE）

**`frontend/src/pages/platforms/index.tsx`**（1559 行，参考 XHS_ALL_IN_ONE 重构）

#### 页面结构

| 组件 | 说明 | 参考 XHS_ALL_IN_ONE |
|------|------|---------------------|
| `PlatformsPage` | 主页面，按平台分组展示账号矩阵 | `accounts-page.tsx` |
| `PlatformGroupCard` | 平台分组卡片（图标 + 计数 + 绑定按钮） | 平台卡片布局 |
| `ConnectionCard` | 连接卡片（Avatar + 状态 Tag + 健康检查） | 账号卡片 + 健康巡检 |
| `AddAccountDrawer` | 添加账号抽屉（Segmented 方式切换） | `add-account-drawer.tsx` |
| `CookieImportPanel` | Cookie 手动导入面板 | `cookie-import-panel.tsx` |
| `QrLoginPanel` | 二维码登录面板（自包含 WebSocket） | `qr-login-panel.tsx` |
| `BrowserLoginPanel` | 浏览器登录面板（自包含 WebSocket） | Playwright 登录 |
| `ApiKeyPanel` | API Key 导入面板 | — |
| `StatusTag` | 状态标签组件（有效/失败/过期） | 状态 Tag |

#### 关键交互改进

- **从 3 个独立 Modal → 1 个 Drawer + Segmented**：Cookie/扫码/浏览器三种方式用分段控件切换
- **健康检查按钮**：每个连接卡片有独立的「检查」按钮，参考 XHS_ALL_IN_ONE 的 Cookie 过期巡检
- **账号矩阵概念**：页面标题改为「账号矩阵」，强调多账号管理
- **统计栏**：Row + Col + Statistic 展示已配置平台/有效连接/失败/过期
- **未配置平台**：紧凑的按钮网格，点击直接打开添加抽屉

#### 支持平台（12 个）

| 平台 | 标识 | 认证方式 | 支持扫码 |
|------|------|---------|---------|
| 小红书 | xhs | Cookie | ✅ |
| 抖音 | douyin | Cookie | ✅ |
| 快手 | kuaishou | Cookie | ✅ |
| B站 | bilibili | Cookie | ✅ |
| 微博 | weibo | Cookie | ❌ |
| 知乎 | zhihu | Cookie | ❌ |
| YouTube | youtube | Cookie | ❌ |
| TikTok | tiktok | Cookie | ❌ |
| X | twitter | Cookie | ❌ |
| OpenAI | openai | API Key | ❌ |
| Anthropic | anthropic | API Key | ❌ |
| MiniMax | minimax | API Key | ❌ |

### 设计决策

- ✅ 三种获取方式全部实现（手动 + Playwright + QrCode）
- ✅ Playwright 默认有头模式，提供切换选项
- ✅ Playwright 作为可选依赖
- ✅ 所有支持平台全覆盖（小红书/抖音/快手/B站/微博/知乎）
- 🔥 **统一凭证存储为 `PlatformConnection`**，废弃 PlatformCookie + SocialMediaConnector
- ✅ 书源 Cookie（BookSource.cookie）和 AI Provider 不纳入统一
- ✅ 参考 XHS_ALL_IN_ONE 的账号矩阵 UI 设计（Drawer + Segmented + 健康检查）
