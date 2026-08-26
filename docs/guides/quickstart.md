# YLCraft 快速上手指南

> 面向刚 fork 仓库、想尽快跑起来并解锁核心能力的开发者。按顺序操作即可。

## 1. 环境要求

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 需带 `venv` 模块 |
| Node.js | 18+ | 推荐 20 LTS |
| Docker + Compose | 任意较新版本 | 仅用于本地 PostgreSQL + Redis |
| FFmpeg | 可选 | 视频/媒体工作流需要 |

## 2. 一键启动

```bash
# Linux / macOS
./start.sh

# Windows
start.bat
```

脚本会自动完成：拉起 PostgreSQL + Redis → 创建 Python 虚拟环境并装依赖 → 复制 `.env` → 执行 Alembic 迁移 → 启动前后端。

启动完成后：

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

也可以手动分步启动，见 [README.md](../../README.md#快速开始)。

## 3. 配置 AI 模型（解锁生成能力）

数据库和 Redis 无需额外配置。但**文本、图片、视频、3D 等生成能力必须接入至少一个模型供应商**，否则工作台只有空壳。

### 3.1 核心模型密钥（推荐优先配置）

核心 LLM / TTS / Embedding 已迁移到数据库驱动，在**设置页 → AI 模型配置**里添加连接器即可，密钥存入数据库而非 `.env`。

仓库提供了一批**免密钥示例连接器**，位于 `examples/ai-connectors/`：

1. 打开前端 **设置 → AI 模型配置**。
2. 使用 **导入（Import）** 动作，选择 `examples/ai-connectors/` 下对应的 `.json`。
3. 编辑导入的连接器，填入你自己的 API Key。

| 文件 | 供应商 | 解锁能力 |
| --- | --- | --- |
| `openai-text-image.json` | OpenAI | 文本 + 图片生成 |
| `siliconflow-text-image.json` | 硅基流动 | 文本 + 图片生成（OpenAI 兼容） |
| `agnes-video-v2.json` | Agnes | 文生视频 |
| `dashscope-wan-2.7-video.json` | 阿里云百炼 | 文/图生视频 |
| `image-to-3d-generic.json` | 通用 | 图转 3D（自填端点） |
| `tencent-hunyuan-3d-pro.json` | 腾讯云 | 图/文转 3D |
| `tencent-hunyuan-rigging.json` | 腾讯云 | 3D 骨骼绑定 |

完整说明见 `examples/ai-connectors/README.md`。

### 3.2 通过 `.env` 配置的密钥（部分功能）

部分功能仍从环境变量读取密钥。编辑 `backend/.env` 并填入：

| 变量 | 用途 |
| --- | --- |
| `MINIMAX_API_KEY` | MiniMax 生图/生视频（`providers.yaml` 默认后端） |
| `OPENAI_API_KEY` | OpenAI 文本/图片/Embedding |
| `QWEN_API_KEY` | 阿里云通义 Embedding（默认向量后端） |
| `HUGGINGFACE_API_KEY` | Hugging Face 图像分割（Live2D 用） |
| `REMOVEBG_API_KEY` | Remove.bg 抠图 |
| `REPLICATE_API_KEY` | Replicate SDXL 风格转换 |

> 优先级：数据库存储的密钥 > `.env` / `providers.yaml` 兜底。

### 3.3 本地 ComfyUI（可选，免费生图）

若不想用云端，可本地跑 ComfyUI，把 `providers.yaml` 里 `image` 默认后端切换到 `comfyui-image`（取消注释 `# image: comfyui-image`），并确认 ComfyUI 服务在 `http://127.0.0.1:8188`。

## 4. 首次使用路径

1. **设置**：添加至少一个文字/图片模型连接器。
2. **创作项目**：新建项目，完成大纲、项目圣经、章节规划。
3. **Writer Room**：在单章内创作正文。
4. **素材中枢 / Prompt 参考库**：加入角色与视觉参考。首次打开「Prompt 参考库」时，如显示空库，点击「同步公开提示词」即可把仓库内置的公开来源同步到本机数据库；提示词正文和图片缓存不会随 Git clone 一起分发，也不会同步任何密钥、项目或私有素材。
5. **生成**：产出正文、脚本、分镜或图片；只有经项目或素材中枢持久化的产物才可追溯。
6. **智能体**：执行工具化工作；写入、删除、发布、高成本动作需显式确认。

需要自由编排视觉工作流时用 **创作画布**。

## 5. 常见问题

- **前端 3000 端口打不开？** 以终端实际输出的 Vite 地址为准。
- **生成按钮无效果 / 报密钥错误？** 检查是否已导入连接器并填入真实 Key；`.env` 改动需重启后端生效。
- **数据库连不上？** 确认 `docker compose up -d postgres redis` 已启动，`pg_isready` 通过。
- **视频功能报 FFmpeg 缺失？** 安装 FFmpeg 并加入 PATH。

## 6. 参与开发

提交 PR 前至少执行：

```bash
python tools/audit_public_release.py
cd frontend && npm run build
```

修改 API、数据模型、Agent Tool、Skill 或工作流时，需同步更新对应 OpenSpec 与架构/API 文档，见 [AGENTS.md](../../AGENTS.md)。
