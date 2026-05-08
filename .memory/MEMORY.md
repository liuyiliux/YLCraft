# YLCraft 长期记忆

> 此目录供其他 AI 读取，包含关键踩坑记录和架构决策。

## 用户
**刘逸流**，偏好中文，指令简短，习惯先理清架构再动手。

## 项目结构（相对路径）
```
YLCraft/
├── backend/app/          # FastAPI 后端
├── frontend/src/        # React + TypeScript 前端
├── DESIGN.md            # 架构圣经
├── PROGRESS.md          # 进度追踪
├── START_HERE.md        # 交接入口
└── .memory/             # 本目录，AI 共享记忆
```

## 架构决策（不可推翻）
- 后端框架：FastAPI
- Agent 框架：LangChain + litellm
- 视频处理：FFmpeg 命令序列
- 数据库：SQLite（开发）→ PostgreSQL（生产）
- 模型统一层：litellm
- Provider 架构：ArcReel Protocol + Registry + YAML 配置
- 三范式并存：Agent(CutClaw) + Pipeline(NarratoAI) + MoE

## 当前进度（截至 2026-05-04）
- ✅ Phase 1：素材资产库 SQLite + SQLModel 数据层
- ✅ Phase 2：素材库前端 + 后台下载任务（轮询 task_id）
- ✅ Phase 4：角色管理模块
- ✅ 抖音下载：iesdouyin 免 Cookie + 多清晰度(bitrate_info) + 文件名优化
- ✅ Live2D 工厂 ~85%：五官绑骨 + 待机动作 + 表情切换 + 视线跟随

## Live2D 五官绑骨（2026-05-04 完成）

### 新增文件
- `backend/app/services/live2d/rigging.py` - 五官绑骨服务

### 新增 API 端点
- `POST /live2d/{model_id}/rig` - 执行面部绑骨
- `GET /live2d/{model_id}/rigging/state` - 获取绑骨状态
- `PUT /live2d/{model_id}/rigging/expression` - 更新表情
- `PUT /live2d/{model_id}/rigging/eye-tracking` - 更新视线跟踪
- `POST /live2d/{model_id}/motion` - 生成待机动作

### 依赖
- numpy, pillow, requests, httpx, aiofiles
- 数据库：`backend/data/ylcraft.db`（非 backend/ylcraft.db）

## 关键踩坑（已解决，务必遵守）

### 抖音下载链路
- **解析**：必须用 iesdouyin.com 方案，yt-dlp 抖音需 Cookie 会失败
- **下载**：CDN直链(v13-cold.douyinvod.com/amemv.com)跳过yt-dlp，用httpx直连
- **多清晰度**：从 `video_info.bitrate_info` 提取 gear_name + 独立 play_addr.url_list，不用 `play_addr.url_list`（那是镜像节点）
- **文件名**：`{title}.mp4`，不要 `douyin_{hash}.mp4`

### B站下载
- `_get_qualities` 必须用**原始分享页 URL** 给 yt-dlp，CDN 直链会 403

### FFmpeg
- 路径从数据库配置读取，不要硬编码

### 大文件下载
- 用 task_id 轮询方案，XHR 会超时（10分钟限制）

### Live2D 数据库
- 数据库文件在 `backend/data/ylcraft.db`，不是 `backend/ylcraft.db`
- 初始化：`from app.db.database import init_db; asyncio.run(init_db())`

## 遇到问题的决策顺序
1. 查 DESIGN.md（架构问题）
2. 查 PROGRESS.md（进度问题）
3. 查参考项目源码（ArcReel / CutClaw / NarratoAI）
4. 问刘逸流

## 开发原则
- 不要承诺豪华功能，聚焦现实范围
- 永远不附加 `&` 启动后台进程
- 先理清架构再动手
