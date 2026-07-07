# YLCraft - 逸流创作平台

> 面向内容创作者的逸流创作平台，覆盖电商/摄影/短剧三大垂直场景，并面向 COSER 提供 Live2D 全自动生产线。

## 目标用户

| 用户类型 | 核心需求 | 代表功能 |
|----------|----------|---------|
| **电商运营** | 商品展示视频批量生成 | 素材库 + 混剪 + 多账号发布 |
| **摄影工作室** | 客片精修 + 写真 MV | AI 修图 + 调色 + 写真 MV 生成 |
| **短剧创作者** | AI 短剧/漫剧生成 | Story Maker + 角色资产 + 分镜 |
| **COSER** | Live2D 模型全自动生产 | Live2D 工厂（立绘 → 绑骨 → VTS） |

## 核心功能

| 功能 | 说明 |
|------|------|
| **爆款拆解** | 输入链接 → 文案结构 + 脚本分镜 + 仿写提示词 |
| **Clip Lab** | AI 视频剪辑（CutClaw Agent / NarratoAI Pipeline / MoE 三种模式） |
| **Story Maker** | AI 短剧漫剧生成（角色 / 场景 / 脚本 / 渲染） |
| **Live2D 工厂** | Live2D 全自动生产线（动漫立绘 / Coser真人 / Coser转二次元 → 抠图 → 分层 → 绑骨 → VTS 导出 → 口型同步） |
| **AI 图像/视频生成** | 多 Provider 统一调度，支持文生图/图生视频 |
| **AI 智能助手** | Agent 模式，支持会话记忆、工具调用、任务编排 |
| **素材采集** | 多平台素材抓取（抖音/B站/小红书/微博/知乎/快手） |
| **小说阅读** | 书架 + 阅读器 + 多书源管理 + 换源 + SSE 流式搜索 |
| **ComfyUI 管理** | 工作流模板管理、任务队列、预设参数 |
| **B站二维码登录** | 扫码登录 + WebSocket 实时推送 + Cookie 自动获取 |
| **UP主分析** | UP主数据统计 + 视频分析 + 粉丝趋势 |
| **我的数据** | 收藏夹管理 + 合集管理 + 观看历史 |
| **评论功能** | 评论分页加载 + 发送评论 + 排序（热度/时间）|
| **字幕功能** | 字幕下载（SRT/ASS/VTT）+ 编辑 + 样式 + 烧录 |

## 技术栈

### 后端

- **框架**: FastAPI + Uvicorn
- **ORM**: SQLModel（同步 + 异步）
- **数据库**: PostgreSQL 16 + pgvector（关系 + 向量 + 全文检索），支持同步/异步双模式
- **Provider 注册表**: 统一调度 LLM / Image / Video / TTS / Live2D
- **AI**: 多 Provider 支持（豆包 LLM/TTS、MiniMax 图生视频、Replicate SDXL、HuggingFace、Remove.bg）
- **连接器**: AI 连接器（OpenAI 兼容协议）+ 社交媒体连接器（抖音/B站/小红书/微博/快手/Instagram/TikTok/Twitter/Threads）
- **视频处理**: FFmpeg + yt-dlp
- **语音识别**: faster-whisper
- **任务队列**: Redis（可选）/ 内存模式自动降级
- **实时通信**: WebSocket 广播

### 前端

- **框架**: React 18 + TypeScript
- **构建工具**: Vite 5
- **UI 库**: Ant Design 5（zh_CN 本地化）
- **路由**: react-router-dom 6
- **HTTP 客户端**: Axios
- **实时通信**: WebSocket (Agent 模块)

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- FFmpeg

### 一键启动

**Linux/macOS:**

```bash
chmod +x start.sh && ./start.sh
```

**Windows:**

```batch
start.bat
```

### 手动启动

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # 编辑 .env 填入 API Key
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npm run dev
```

### 访问地址

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

## 配置说明

### 环境变量（`backend/.env`）

```bash
# MiniMax API（图生视频）
MINIMAX_API_KEY=your_minimax_api_key_here

# Live2D 抠图（Remove.bg）
# REMOVEBG_API_KEY=your_removebg_api_key_here

# Live2D 风格转换（Replicate SDXL）
# REPLICATE_API_KEY=your_replicate_api_key_here

# Live2D 图像分割（HuggingFace）
# HUGGINGFACE_API_KEY=your_huggingface_api_key_here

# （可选）抖音 Cookie - 用于高清/私密内容解析
# DOUYIN_COOKIE=session_id=xxx; sessionid=xxx

# （可选）B站 Cookie
# BILIBILI_COOKIE=SESSDATA=xxx; bili_jct=xxx
```

### Provider 注册表（`backend/config/providers.yaml`）

定义所有 AI Provider 的模型、端点、默认值。支持 `${ENV_VAR}` 环境变量注入。系统会自动加载并注册。

### API 密钥管理

API 密钥优先从数据库读取（PostgreSQL `api_keys` 表，由 `ApiKeyStore` 加密存储），支持前端配置页面热更新；兜底从环境变量读取。

## 项目结构

```
YLCraft/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── main.py            # FastAPI 入口 & 生命周期管理（30+ API 模块）
│   │   ├── api/v1/            # REST API 路由（30+ 模块）
│   │   ├── services/          # 业务逻辑层
│   │   │   ├── agent/         # AI Agent（记忆/会话/工具调用）
│   │   │   ├── asset/         # 统一素材资产库
│   │   │   ├── breaker/       # 爆款拆解
│   │   │   ├── clip/          # Clip Lab（CutClaw/NarratoAI/MoE）
│   │   │   ├── story/         # Story Maker
│   │   │   ├── live2d/        # Live2D 工厂（抠图/分层/绑骨/VTS/口型同步）
│   │   │   ├── llm/           # LLM Manager & Provider 注册表
│   │   │   ├── video/         # 视频下载解析（抖音/B站/Twitter）
│   │   │   ├── video_gen/     # AI 视频生成（MiniMax等）
│   │   │   ├── image/         # 图像生成后端
│   │   │   ├── comfyui/       # ComfyUI 客户端/池/工作流
│   │   │   ├── crawler/       # 多平台素材采集
│   │   │   ├── novel/         # 小说阅读（书架/下载/爬虫）
│   │   │   ├── subtitle/       # 字幕提取（faster-whisper）
│   │   │   ├── bgm/           # BGM 配乐
│   │   │   ├── character/     # 角色管理
│   │   │   ├── platform_connection/    # 平台连接（旧版）
│   │   │   ├── social_media_connector/ # 社交媒体连接器（新版）
│   │   │   └── ai_connector/  # AI 连接器管理
│   │   ├── connectors/        # 连接器实现
│   │   │   ├── ai/            # AI 连接器（OpenAI 兼容协议）
│   │   │   └── social/        # 社交媒体连接器（9 平台）
│   │   ├── core/              # 核心模块（配置/任务队列/WebSocket）
│   │   │   └── contracts/     # 类型契约
│   │   └── db/                # 数据库层
│   │       ├── database.py    # PostgreSQL 16 同步+异步引擎（asyncpg / psycopg2）
│   │       └── models/        # 16+ 数据模型
│   ├── config/                # 配置文件
│   │   ├── providers.yaml     # Provider 注册表
│   │   └── live2d.json        # Live2D 处理模式配置
│   ├── data/                  # 运行时数据（Cookie、素材文件等）
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── App.tsx            # 路由入口（27 页面）
│   │   ├── pages/             # 页面组件（27 页面）
│   │   ├── components/        # 通用组件 & Live2D 查看器
│   │   ├── api/               # API 调用层
│   │   ├── hooks/             # 自定义 Hooks（WebSocket）
│   │   ├── context/           # React Context（Agent）
│   │   ├── constants/         # 主题配置（亮/暗）
│   │   └── types/             # TypeScript 类型
│   ├── package.json
│   └── vite.config.ts
├── docs/                       # 项目文档（DESIGN / rules / architecture / agent / platform / guides / reference）
├── .cnb.yml                    # CI/CD 流水线
└── start.sh / start.bat        # 启动脚本
```

## API 模块（完整）

| 路由前缀 | 功能 | 标签 |
|----------|------|------|
| `/api/v1/agent` | AI 智能助手 | Agent |
| `/api/v1/breaker` | 爆款拆解 | Breaker |
| `/api/v1/clip` | 视频剪辑（NarratoAI / MoE） | Clip — NarratoAI / MoE |
| `/api/v1/clip/cutclaw` | CutClaw Agent 剪辑 | Clip — CutClaw |
| `/api/v1/clip-ops` | 剪辑操作 | Clip Operations |
| `/api/v1/story` | Story Maker | Story Maker |
| `/api/v1/live2d` | Live2D 工厂 | Live2D Factory |
| `/api/v1/images` | 图像生成 | Images |
| `/api/v1/videos` | 视频生成 | Videos |
| `/api/v1/tts` | TTS 语音合成 | TTS |
| `/api/v1/llm` | LLM 调用 | LLM |
| `/api/v1/download` | 视频下载解析 | Download |
| `/api/v1/image-editor` | 图片编辑 | Image Editor |
| `/api/v1/assets` | 素材资产库 | Assets |
| `/api/v1/characters` | 角色管理 | Characters |
| `/api/v1/comfyui` | ComfyUI 管理 | ComfyUI |
| `/api/v1/bgm` | BGM 配乐 | BGM |
| `/api/v1/subtitles` | 字幕管理 | Subtitles |
| `/api/v1/crawler` | 素材采集 | Crawler |
| `/api/v1/novels` | 小说阅读 | Novels |
| `/api/v1/providers` | Provider 管理 | Providers |
| `/api/v1/ai` | AI 连接器管理（新版） | AI Connectors |
| `/api/v1/social` | 社交媒体连接器（新版） | Social Media Connectors |
| `/api/v1/platforms` | 平台连接（旧版兼容） | Platform Connections (Legacy) |
| `/api/v1/cookies` | Cookie 管理 | Cookies |
| `/api/v1/tasks` | 任务管理 | Tasks |
| `/api/v1/ws` | WebSocket 实时推送 | WebSocket |
| `/api/v1/settings` | 系统设置 | Settings |

## 前端页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | Dashboard | 仪表盘 |
| `/breaker` | 爆款拆解 | 链接解析 → 文案结构 + 仿写 |
| `/clip` | Clip Lab | AI 视频剪辑主面板 |
| `/clip-ops` | 剪辑操作 | 精细化剪辑调整 |
| `/story` | Story Maker | AI 短剧/漫剧生成 |
| `/live2d` | Live2D 工厂 | 模型生成全流程 |
| `/image-gen` | 图像生成 | 文生图/图生图 |
| `/video-gen` | 视频生成 | 图生视频/AI 视频 |
| `/comfyui` | ComfyUI | 工作流管理 |
| `/download` | 视频下载 | 多平台视频解析下载 |
| `/assets` | 素材库 | 统一素材资产管理 |
| `/characters` | 角色管理 | 角色资产 CRUD |
| `/subtitle` | 字幕管理 | 提取 + 样式编辑 |
| `/bgm` | BGM 配乐 | 内置 + 上传管理 |
| `/agent` | AI 助手 | 智能对话 + 工具调用 |
| `/platforms` | 平台连接 | 社交媒体绑定 |
| `/publish` | 内容发布 | 多平台一键发布 |
| `/crawler` | 素材采集 | 多平台自动抓取 |
| `/novel-bookshelf` | 书架 | 小说书架管理 |
| `/novel-search` | 小说搜索 | 多书源搜索 |
| `/novel-reader` | 阅读器 | 在线阅读 |
| `/image-editor` | 图片编辑 | 裁剪/滤镜/调色 |
| `/tasks` | 任务中心 | 异步任务进度 |
| `/settings` | 系统设置 | 全局配置 |

## CI/CD

项目通过 `.cnb.yml` 配置自动构建检查流水线，在每次 push 时自动执行：

- **后端检查**: 安装依赖并验证 FastAPI 应用可正常导入
- **前端检查**: `npm ci` + `npm run build`，仅在前端文件变更时触发

## 支持平台

### 视频下载解析

| 平台 | 支持程度 |
|------|----------|
| 抖音 | ✅ CDN 直链解析（多清晰度） |
| B站 | ✅ yt-dlp |
| Twitter/X | ✅ 内置解析器 |

### 社交媒体连接器

| 平台 | 状态 |
|------|------|
| 抖音 | ✅ |
| B站 | ✅ |
| 小红书 | ✅ |
| 微博 | ✅ |
| 快手 | ✅ |
| Instagram | ✅ |
| TikTok | ✅ |
| Twitter/X | ✅ |
| Threads | ✅ |

### AI Provider

| Provider | 用途 |
|----------|------|
| MiniMax | 图像生成 / 视频生成 |
| Replicate (SDXL) | Live2D 风格转换 |
| Remove.bg | Live2D 抠图 |
| HuggingFace | Live2D 图像分割 |
| ComfyUI | 本地/远程图像生成 |

## 处理模式

Live2D 工厂各环节支持本地模型和云端 API 双模式，可通过配置文件或前端界面切换：

| 环节 | 本地模式 | API 模式 |
|------|----------|----------|
| 抠图（Rembg） | rembg 本地模型 | Remove.bg API |
| 风格转换 | 本地 SD 模型 | Replicate SDXL API |
| 图像分割 | 本地模型 | HuggingFace Inference API |

## 更多文档

### 核心文档

| 文档 | 说明 |
|------|------|
| [DESIGN](docs/DESIGN.md) | 总体设计与架构（单一事实来源：产品定位、技术栈、模块现状、文档导航） |
| [Agent Skill Runtime](docs/agent/agent-skill-runtime.md) | Agent Skill 文件化运行时规范（加载 / 路由 / Bundle / 草稿审批） |
| [Agent Center 使用说明](docs/agent/agent-center.md) | 智能体工作台使用指南 |
| [B站功能指南](docs/platform/BILIBILI_GUIDE.md) | B站登录 / 下载 / 弹幕 / 评论等实现与优化清单 |
| [多平台项目参考](docs/platform/MULTI_PLATFORM_REFERENCE.md) | 多平台采集与发布开源项目参考 |
| [创作项目闭环](docs/guides/creative-project-loop.md) | 产品主链路与模块状态治理 |

### 规范与架构（docs/）

- `rules/`：项目规范（01 项目概述 / 02 后端 / 03 前端 / 04 代码风格 / 05 快速参考 / 06 数据库设计），权威且注入为工作区规则。
- `architecture/`：子领域架构设计（资产中枢、AI 服务层、Live2D、多平台 API 等）。
- `devlog/`：只保留必要的最新交接记录；长期事实要回写到架构、接口或领域文档。
- `refactor/`：重构 / 迁移计划。
- `reference/`：外部参考与客户素材，如 `docs/reference/REF_PROJECTS.md`、`docs/reference/短剧/`（分镜脚本、立绘提示词、微短剧拆解；`.rtf`/`.docx` 二进制原样保留，`images/` 存放配图）。

> 历史交接入口已并入 `docs/devlog/`；前端样式以 `docs/rules/03` 为准，进度与实现状态以 `docs/DESIGN.md` 第四节为准。

## License

MIT

## 作者

怪盗LYL
