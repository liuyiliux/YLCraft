## ADDED Requirements

### Requirement: 项目技术栈定义
AI 助手 SHALL 使用以下技术栈信息作为项目上下文基础：

| 维度 | 技术选型 |
|------|---------|
| 后端框架 | FastAPI + Uvicorn |
| ORM | SQLModel（同步 + 异步双模式） |
| 数据库 | SQLite（aiosqlite），路径：`backend/data/ylcraft.db` |
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite 5 |
| UI 库 | Ant Design 5（zh_CN 本地化） |
| 路由 | react-router-dom 6 |
| HTTP 客户端 | Axios / 原生 fetch |
| 任务队列 | Redis（可选）/ 内存模式自动降级 |
| 视频处理 | FFmpeg + yt-dlp |
| 语音识别 | faster-whisper |

#### Scenario: AI 引用技术栈信息
- **WHEN** AI 助手需要了解项目使用的技术栈
- **THEN** SHALL 从本规范获取准确的技术选型信息，不得臆测

### Requirement: 后端目录结构规范
AI 助手 SHALL 遵循以下后端目录结构约定：

```
backend/
├── app/
│   ├── main.py                   # FastAPI 入口 & 生命周期管理
│   ├── api/v1/                   # REST API 路由（按功能模块组织）
│   ├── services/                 # 业务逻辑层（按领域组织）
│   │   ├── llm/                  # LLM Manager & Provider 注册表
│   │   ├── image/                # 图像生成服务
│   │   ├── video/                # 视频下载解析服务
│   │   ├── crawler/              # 多平台素材采集
│   │   ├── platform_connection/  # 平台连接（B站等）
│   │   └── cookies/             # Cookie 管理
│   ├── core/                    # 核心模块（config、task_queue、ws_manager）
│   ├── connectors/              # 连接器实现（ai/、social/）
│   └── db/                      # 数据库层（models/）
├── config/                      # 配置文件（providers.yaml、live2d.json）
└── data/                        # 运行时数据（SQLite DB、settings.json）
```

#### Scenario: 定位后端代码位置
- **WHEN** AI 助手需要定位某类功能的代码位置
- **THEN** SHALL 按上述目录结构约定查找，如 API 路由在 `api/v1/`、业务逻辑在 `services/`

### Requirement: 已实现功能模块清单
AI 助手 SHALL 知晓当前已实现的核心功能模块：

**已实现（可用）：**
- **模型配置管理**：Provider 注册表（`config/providers.yaml`），支持 LLM/Image/TTS/Video/Live2D 多类型 Provider，API Key 加密存储
- **AI 图片生成**：ComfyUI 工作流驱动，支持 SDXL/Flux 等模型，Prompt 模板系统
- **B站视频搜索与下载**：搜索 API + yt-dlp 下载，支持 Cookie 认证
- **B站账号登录**：二维码登录流程，Cookie 自动获取与管理（Patchright）

**规划中（不可用）：**
- Story Maker、Live2D 工厂、Clip Lab、爆款拆解、Agent 系统

#### Scenario: 功能可用性判断
- **WHEN** AI 助手被要求修改或扩展某功能
- **THEN** SHALL 先判断该功能是否在「已实现」列表中，规划中的功能 SHALL 标注不可用

### Requirement: 前端页面路由映射
AI 助手 SHALL 了解前端 27 个页面的路由结构：

| 路由路径 | 页面名称 | 功能描述 |
|----------|---------|---------|
| `/` | Home | 首页仪表盘 |
| `/model-config` | ModelConfig | 模型配置管理 |
| `/image-gen` | ImageGen | AI 图片生成 |
| `/bilibili/login` | BilibiliLogin | B站账号登录 |
| `/bilibili/search` | BilibiliSearch | B站视频搜索 |
| `/bilibili/download` | BilibiliDownload | B站视频下载 |

#### Scenario: 定位前端页面
- **WHEN** AI 助手需要找到特定功能的前端页面
- **THEN** SHALL 通过路由路径定位到 `frontend/src/pages/` 下对应组件

### Requirement: 数据模型概览
AI 劥手 SHALL 掌握核心数据模型的用途：

| 模型名 | 表名 | 用途 |
|--------|------|------|
| ProviderConfig | provider_configs | AI Provider 配置（LLM/Image/TTS/Video） |
| ApiKeyStore | api_keys | API 密钥加密存储 |
| PlatformAccount | platform_accounts | 社交平台账号绑定 |
| VideoTask | video_tasks | 视频下载任务 |
| ImageGenerationTask | image_gen_tasks | 图片生成任务记录 |
| CookieData | cookies | 平台 Cookie 存储 |
| SystemSettings | system_settings | 系统运行配置 |

#### Scenario: 数据操作上下文
- **WHEN** AI 助手需要进行数据库相关开发
- **THEN** SHALL 参考上述模型列表选择正确的 SQLModel 类，不得自行发明不存在的模型
