## Requirements

### Requirement: 常用开发命令速查
AI 助手 SHALL 掌握以下常用命令：

| 命令 | 说明 |
|------|------|
| `start.bat` | Windows 一键启动脚本 |
| `start.sh` | Linux/Mac 一键启动脚本 |
| `cd backend && uvicorn app.main:app --reload --port 8000` | 启动后端开发服务器 |
| `cd frontend && npm run dev` | 启动前端开发服务器 |
| `cd frontend && npm run build` | 构建前端生产版本 |
| `cd backend && python -m pytest tests/` | 运行测试（如有） |
| `openspec new change "<name>"` | 创建新变更 |
| `openspec status --change "<name>"` | 查看变更状态 |

#### Scenario: 执行开发命令
- **WHEN** 需要执行构建、启动或测试操作
- **THEN** SHALL 使用上述命令模板，根据实际情况调整参数

### Requirement: 关键路径映射速查
AI 助手 SHALL 维护以下关键文件的快速索引：

**后端核心入口：**
| 文件 | 用途 |
|------|------|
| `backend/app/main.py` | FastAPI 应用入口、路由注册、生命周期 |
| `backend/app/core/config.py` | 配置管理核心类（ProvidersConfig、ApiKeyStore） |
| `backend/config/providers.yaml` | Provider 注册表（模型/端点/默认值） |
| `backend/app/data/settings.json` | 系统运行时设置 |

**数据库相关：**
| 文件 | 用途 |
|------|------|
| `backend/app/db/database.py` | 数据库引擎（同步+异步）、Session 工厂 |
| `backend/app/db/models/` | 所有 SQLModel 模型定义 |
| `backend/data/ylcraft.db` | SQLite 数据库文件 |

**前端核心入口：**
| 文件 | 用途 |
|------|------|
| `frontend/src/App.tsx` | 路由配置（27个页面路由） |
| `frontend/src/api/` | API 调用封装 |
| `frontend/src/types/` | TypeScript 类型定义 |
| `frontend/vite.config.ts` | Vite 构建配置、代理设置 |

#### Scenario: 快速定位文件
- **WHEN** 需要查找某个功能的实现位置
- **THEN** SHALL 优先查阅本路径映射表，缩小搜索范围

### Requirement: 环境变量参考
AI 助手 SHALL 了解项目使用的环境变量：

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `DATABASE_URL` | SQLite 数据库路径 | `sqlite:///./data/ylcraft.db` |
| `OPENAI_API_KEY` | OpenAI API Key（可通过配置覆盖） | 无 |
| `COMFYUI_URL` | ComfyUI 服务地址 | `http://127.0.0.1:8188` |
| `REDIS_URL` | Redis 连接地址（可选） | 无（降级为内存队列） |
| `DOWNLOAD_DIR` | 文件下载保存目录 | `./downloads` |
| `CORS_ORIGINS` | 允许的前端跨域来源 | `http://localhost:5173` |

环境变量可在 `providers.yaml` 中通过 `${VAR_NAME}` 语法引用。

#### Scenario: 配置环境相关选项
- **WHEN** 涉及外部服务连接或路径配置
- **THEN** SHALL 优先使用环境变量或配置文件，不得硬编码

### Requirement: API 端点速查
AI 助手 SHALL 了解核心 API 端点分组：

| 模块 | 前缀 | 关键端点 |
|------|------|---------|
| 模型配置 | `/api/v1/models` | `GET /list`, `POST /configure`, `PUT /{id}` |
| 图片生成 | `/api/v1/images` | `POST /generate`, `GET /tasks/{id}`, `GET /result/{id}` |
| B站登录 | `/api/v1/bilibili/auth` | `GET /qrcode`, `POST /check`, `GET /status` |
| B站搜索 | `/api/v1/bilibili/search` | `GET /videos`, `GET /users` |
| 视频下载 | `/api/v1/videos` | `POST /download`, `GET /tasks`, `GET /tasks/{id}` |
| Cookie | `/api/v1/cookies` | `GET /list`, `POST /refresh`, `DELETE /{id}` |
| 系统设置 | `/api/v1/settings` | `GET /`, `PUT /` |

#### Scenario: 构建 API 请求
- **WHEN** 前端需要调用后端 API
- **THEN** SHALL 参考上表确定正确的 HTTP 方法和 URL 路径

### Requirement: 调试技巧参考
调试问题时 SHALL 按以下优先级排查：
1. **检查日志**：后端日志输出到控制台，查看是否有异常堆栈
2. **验证配置**：确认 `providers.yaml` 和 `settings.json` 格式正确
3. **数据库状态**：使用 SQLite 工具直接查询 `ylcraft.db` 验证数据
4. **网络连通性**：确认 ComfyUI/B站 API 等外部服务可达
5. **Cookie 有效性**：B站功能需确保 Cookie 未过期，可通过 `/api/v1/bilibili/auth/status` 检查
6. **前端代理**：开发环境下 Vite 代理配置在 `vite.config.ts`，确认代理目标正确

#### Scenario: 排查问题
- **WHEN** 遇到功能异常或报错
- **THEN** SHALL 按上述步骤逐一排查，从最常见的原因开始
