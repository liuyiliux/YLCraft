# YLCraft

> 一个把创意、参考素材和 AI 生成结果沉淀为可复用资产的开源内容生产工作台。

YLCraft 面向不想只停留在聊天框里的内容创作者：小说与短剧团队、摄影师、COSER、电商运营和自媒体创作者。它将素材中枢、创作项目、可视化工作流、模型配置与 Agent + Skill Runtime 连接为一个可持续使用的创作环境。

## 界面预览

### 内容生产中枢

从一个轻量的概览进入创作、素材、图像、视频、下载、剪辑和发布等工作区。

![YLCraft 内容生产中枢概览](docs/images/home-dashboard-preview.png)

### 内容采集

按平台、媒体类型、排序和时长检索公开内容，将可用参考纳入后续项目和素材工作流。

![YLCraft 内容搜索与采集](docs/images/content-search-preview.png)

### 创作画布

将参考图、Prompt、模型和批量生成组织为可追踪的类型化节点工作流；结果可回流到创作项目和素材中枢。

![YLCraft 创作画布：参考图逐图批量生成工作流](docs/images/canvas-workflow-preview.png)

相比“AI 对话 + 一堆提示词文件”，YLCraft 围绕三件实际的事设计：

1. **降低门槛**：用户面对项目、角色、章节、参考图和产物，而不需要先理解 Tool schema、Prompt 管线或运行记录。
2. **直观展示**：版本、执行轨迹、生成媒体、来源证据和素材血缘在对应业务工作台里可见、可比较、可继续操作。
3. **节省 Token**：下载、导入、格式转换、校验、批处理和持久化等确定性工作由服务与脚本完成；模型专注理解、规划和创作。

## 当前可用能力

| 工作区 | 能力 |
| --- | --- |
| **素材中枢** | 导入、存储、检索、版本化图片、视频、音频、文本和生成结果，并保留来源与血缘。 |
| **创作项目** | 从创意进入大纲、项目圣经、章节规划、正文、脚本、分镜、参考卡和生成媒体。 |
| **Story Cockpit / Writer Room** | 支持场景节拍、角色演绎、正文候选、人味润色、审稿、连续性事实、伏笔和受控提升为正式正文。 |
| **创作画布** | 独立的节点式工作流画布，编排文本、Prompt、模型、图片、平台搜索、图片处理、批量生图和类型化变量连线。 |
| **Prompt 参考库** | 浏览本地优先缓存的双语提示词、标签、模型分组与参考图，并插入画布和生图流程。 |
| **AI 模型配置** | 通过统一连接器配置 LLM、图像、视频、TTS、STT 与 Embedding 模型。 |
| **智能体与 Skills** | 提供 thread 对话、上下文快照、记忆、工具轨迹、文件化 Skill 与 Supervisor 子智能体委派。 |
| **采集与发布** | 提供平台搜索、下载与导入、任务诊断，以及已接入平台上的受控发布能力。 |

## 产品主链路

```mermaid
flowchart LR
  Idea["创意或外部参考"] --> Project["创作项目"]
  Search["搜索 / 下载 / 导入"] --> Assets["素材中枢"]
  Project --> Content["大纲 / 章节 / 正文 / 脚本 / 分镜"]
  Assets --> Content
  Content --> Generate["AI 文本 / 图片 / 视频生成"]
  Generate --> Assets
  Project --> Agent["Agent + Skills"]
  Assets --> Agent
  Agent --> Project
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- PostgreSQL 16 + pgvector
- Redis 可选。本地开发时任务队列会降级到内存模式
- 视频与媒体工作流需要 FFmpeg

### 1. 启动本地基础设施（单容器：PostgreSQL + Redis）

仓库中的 Compose 文件只用于启动本地基础设施，将 PostgreSQL 与 Redis 合并为单个容器，一条命令即可全部启动：

```bash
docker compose up -d --build
```

其中凭证只适合本地开发。不要暴露数据库端口，也不要在共享或生产环境复用该开发密码。

> **注意**：这里的「单容器」指 Docker Compose 把 PostgreSQL + Redis 合并为一个容器。
> 它和 CNB **云原生开发的单容器模式**（开发环境与 code-server 运行在同一容器）是两个不同概念，勿混淆。

### 1.1 使用 CNB 云原生开发（单容器模式）

仓库通过 `.cnb.yml` 的 `vscode` 事件与 `.ide/Dockerfile` 提供 CNB 云原生开发环境。
`.ide/Dockerfile` 已安装 `code-server`，因此采用**单容器模式**启动：
开发环境与 code-server 运行在同一容器内，既可直接使用 WebIDE，也可通过 VSCode 远程开发。

点击 CNB 仓库页面的「云原生开发」按钮即可一键进入开发环境。

### 2. 配置后端

```bash
cd backend
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑 `backend/.env`，填入数据库连接和准备使用的模型供应商配置。API Key、Cookie、浏览器导出文件和本地凭证必须只保存在被忽略的本地文件中。

### 3. 执行迁移并启动 API

```bash
cd backend
python -m venv venv
# Linux/macOS
source venv/bin/activate
# Windows PowerShell
# .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:3000`，或以终端实际输出的 Vite 地址为准。API 文档在 `http://127.0.0.1:8000/docs`。

### 可选：初始化小说阅读子模块

```bash
git submodule update --init --recursive
```

## 首次使用建议

1. 进入 **设置**，添加文字或图片模型连接器。
2. 在 **创作项目** 新建项目。
3. 完成大纲、项目圣经与章节规划，再在单章的 **Writer Room** 中创作。
4. 从 **素材中枢** 或 **Prompt 参考库** 加入角色和视觉参考。
5. 生成正文、脚本、分镜或图片。只有通过项目或素材中枢持久化的产物，才会成为可追溯素材。
6. 使用 **智能体** 执行工具化工作；写入、删除、发布和高成本动作仍要求显式确认。

需要自由编排视觉工作流时，使用 **创作画布**。画布与项目关系图谱刻意分离：画布负责组织可复用流程，项目和素材中枢仍是业务事实与血缘的唯一来源。

## 架构速览

```text
frontend/                   React 18 + TypeScript + Vite + Ant Design
backend/app/api/v1/         FastAPI HTTP 边界
backend/app/services/       Agent、项目、素材、AI、画布与平台等领域服务
backend/app/db/models/      SQLModel 数据模型
backend/alembic/            数据库迁移
backend/app/skills/         内置文件化 Skills
docs/architecture/          系统与 API 的事实来源文档
openspec/changes/           进行中与已归档的实现规格
```

- **前端**：React、TypeScript、Vite、Ant Design。
- **后端**：FastAPI、SQLModel、PostgreSQL + pgvector、Alembic。
- **AI 与集成**：可配置供应商连接器、适用场景下的 OpenAI 兼容协议、ComfyUI、媒体工具、平台适配器与任务诊断。

## 安全与合规使用

- 不要提交 `.env`、供应商密钥、Cookie、浏览器导出文件、数据库导出、生成媒体、本地备份、日志、证书或私钥。
- 将 `backend/.env.example` 复制为本地 `.env` 使用；示例文件可提交，`.env` 已被忽略。
- 贡献或发布前运行：

  ```bash
  python tools/audit_public_release.py
  ```

- 漏洞报告见 [SECURITY.md](SECURITY.md)，完整发布检查见 [docs/SECURITY_RELEASE.md](docs/SECURITY_RELEASE.md)。
- 平台接入只能用于你有权使用的账号、数据和权限范围。不要在 Issue、PR 或日志中提交真实账号 Cookie。

## 文档入口

| 文档 | 用途 |
| --- | --- |
| [文档地图](docs/README.md) | 维护中的文档结构入口。 |
| [系统架构](docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md) | 产品边界、运行时模型、数据归属和模块状态。 |
| [API 清单](docs/architecture/API_SURFACE.md) | 当前 HTTP API 契约。 |
| [创作项目指南](docs/guides/creative-project-loop.md) | 项目、内容、素材与生成工作流。 |
| [智能体中心](docs/agent/agent-center.md) | 对话工作台与运行时行为。 |
| [Agent Skill Runtime](docs/agent/agent-skill-runtime.md) | Skill 包、路由与审批契约。 |
| [AI 协作协议](docs/AI_HANDOFF_PROTOCOL.md) | 多电脑、多 AI 协作开发规则。 |

## 开发约定

提交 PR 前至少执行：

```bash
python tools/audit_public_release.py
cd frontend && npm run build
```

修改 API、数据模型、Agent Tool、Skill 或工作流时，应在同一改动中更新其所属 OpenSpec 与架构/API 文档。详见 [AGENTS.md](AGENTS.md)。

## 许可证

尚未选定许可证。在添加 `LICENSE` 文件之前，仓库默认不授予开源复用许可。
