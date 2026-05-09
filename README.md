# YLCraft - 超级自媒体平台

> 面向内容创作者的超级自媒体平台，覆盖电商/摄影/短剧三大垂直场景，并面向 COSER 提供 Live2D 全自动生产线。

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

## 技术栈

### 后端

- **框架**: FastAPI + Uvicorn
- **ORM**: SQLModel
- **数据库**: SQLite (aiosqlite)
- **AI**: 多 Provider 支持（豆包 LLM/TTS、MiniMax 图生视频等）
- **视频处理**: FFmpeg + yt-dlp
- **语音识别**: faster-whisper

### 前端

- **框架**: React 18 + TypeScript
- **构建工具**: Vite 5
- **UI 库**: Ant Design 5
- **HTTP 客户端**: Axios
- **实时通信**: WebSocket

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

## 环境变量

在 `backend/.env` 中配置：

```bash
# 豆包 API（LLM + TTS）
DOUBAO_API_KEY=your_doubao_api_key_here

# MiniMax API（图生视频）
MINIMAX_API_KEY=your_minimax_api_key_here

# （可选）抖音 Cookie - 用于高清/私密内容解析
# DOUYIN_COOKIE=session_id=xxx; sessionid=xxx

# （可选）B站 Cookie
# BILIBILI_COOKIE=SESSDATA=xxx; bili_jct=xxx
```

## 项目结构

```
YLCraft/
├── backend/                 # 后端服务
│   ├── app/
│   │   ├── main.py         # FastAPI 入口
│   │   ├── api/v1/         # REST API 路由
│   │   ├── services/       # 业务逻辑层
│   │   ├── core/           # 核心模块（配置、任务队列、WebSocket）
│   │   ├── db/             # 数据库层
│   │   └── connectors/     # AI/社交平台连接器
│   ├── config/             # 配置文件
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # 前端应用
│   ├── src/
│   │   ├── pages/          # 页面组件
│   │   ├── components/     # 通用组件
│   │   ├── api/            # API 调用层
│   │   ├── hooks/          # 自定义 Hooks
│   │   └── types/          # TypeScript 类型
│   ├── package.json
│   └── vite.config.ts
├── docs/                    # 项目文档
└── start.sh / start.bat     # 启动脚本
```

## API 模块

| 路由前缀 | 功能 |
|----------|------|
| `/api/v1/agent` | AI 智能助手 |
| `/api/v1/breaker` | 爆款拆解 |
| `/api/v1/clip` | 视频剪辑 |
| `/api/v1/clip-ops` | 剪辑操作 |
| `/api/v1/story` | Story Maker |
| `/api/v1/live2d` | Live2D 工厂 |
| `/api/v1/images` | 图像生成 |
| `/api/v1/videos` | 视频生成 |
| `/api/v1/tts` | TTS 语音合成 |
| `/api/v1/download` | 视频下载解析 |
| `/api/v1/image-editor` | 图片编辑 |
| `/api/v1/assets` | 素材资产库 |
| `/api/v1/characters` | 角色管理 |
| `/api/v1/comfyui` | ComfyUI 管理 |
| `/api/v1/bgm` | BGM 配乐 |
| `/api/v1/subtitles` | 字幕管理 |
| `/api/v1/crawler` | 素材采集 |
| `/api/v1/platforms` | 平台连接 |
| `/api/v1/settings` | 系统设置 |

## 更多文档

| 文档 | 说明 |
|------|------|
| [START_HERE](docs/START_HERE.md) | 项目交接入口 |
| [DESIGN](docs/DESIGN.md) | 完整架构设计 |
| [PROGRESS](docs/PROGRESS.md) | 开发进度追踪 |
| [FRONTEND_STYLE_GUIDE](docs/FRONTEND_STYLE_GUIDE.md) | 前端开发规范 |

## License

MIT
