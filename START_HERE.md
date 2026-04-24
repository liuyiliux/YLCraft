# YLCraft 项目交接

## 项目定位
**YLCraft** — 超级自媒体平台，支持电商/摄影/短剧三大垂直场景的内容创作。
GitHub: https://cnb.cool/yiliu/YLCraft

## 必读文档（优先级顺序）
1. `START_HERE.md` — 本文件，交接入口
2. `DESIGN.md` — 项目设计基准，v0.2.0，超级自媒体平台完整架构
3. `PROGRESS.md` — 当前开发进度
4. `.memory/MEMORY.md` — 关键踩坑记录和架构决策（其他 AI 可读）

## 技术栈
- 后端：FastAPI + Python，路径 `backend/`
- 前端：React + TypeScript + Vite + AntDesign，路径 `frontend/`
- 数据库：SQLite（开发）→ PostgreSQL（规划）
- 启动：`start.bat` 同时启动后端(uvicorn)+前端(npm run dev)
- 端口：后端 8000，前端 5173

## 核心架构
- BackendManager：Provider 注册表模式，litellm 统一调用
- 三大功能：爆款拆解(Breaker) / Clip Lab / Story Maker
- 统一素材资产库(Asset Library)：视频/图片/音频/文档统一管理
- 参考项目（已 clone）：`refs/`
  - Jellyfish / ArcReel / CutClaw / NarratoAI / montage-ai / MoneyPrinterTurbo

## 当前进度
- ✅ Phase 1：素材资产库（Asset Library）SQLite + SQLModel 数据层
- ✅ Phase 2：素材库前端 + 后台下载任务（轮询 task_id）
- ✅ Phase 4：角色管理模块
- ✅ 抖音下载：iesdouyin 免 Cookie 方案 + 多清晰度(bitrate_info) + 文件名优化
- ⬜ 待做：素材库改名(素材库→资产库) + 角色整合进统一资产库

## 开发原则
1. 先查 DESIGN.md（架构问题）
2. 查 PROGRESS.md（进度问题）
3. 查参考项目源码（ArcReel/CutClaw/NarratoAI）
4. 再问刘逸流
5. 不要承诺豪华功能，聚焦现实范围
6. 永远不附加 `&` 启动后台进程

## 关键踩坑（已解决）
- 抖音解析：必须用 iesdouyin.com 方案，yt-dlp 抖音需 Cookie 会失败
- 抖音下载：CDN直链(v13-cold.douyinvod.com)跳过yt-dlp，用httpx直连
- 多清晰度：从 video_info.bitrate_info 提取（gear_name+独立play_addr），不用url_list
- FFmpeg路径：从数据库配置读取，不要硬编码
- 大文件下载：用 task_id 轮询方案，XHR会超时

## 如何继续开发
1. 阅读 START_HERE.md（本文件）
2. 阅读 DESIGN.md 理解完整架构
3. 阅读 .memory/MEMORY.md 了解关键踩坑和决策
4. 查看当前代码：`backend/app/` 和 `frontend/src/`
5. 按 Phase 1/2/3 顺序推进
6. 每次提交写清楚改动，push 到 origin/master

## 项目结构
```
YLCraft/
├── DESIGN.md              # 架构圣经
├── PROGRESS.md            # 进度追踪
├── START_HERE.md          # 本文件，AI/开发者入口
├── start.bat              # 启动脚本（后端+前端）
├── backend/
│   └── app/
│       ├── main.py        # FastAPI 入口
│       ├── api/v1/        # REST API
│       ├── services/      # 业务逻辑
│       │   ├── llm/       # BackendManager / Provider 注册表
│       │   ├── asset/     # 统一素材资产库
│       │   ├── download/  # 下载服务
│       │   ├── breaker/   # 爆款拆解
│       │   ├── clip/      # Clip Lab
│       │   └── story/     # Story Maker
│       └── db/
│           ├── database.py  # SQLite + SQLModel
│           └── models/      # 数据模型
├── frontend/
│   └── src/
│       ├── pages/          # 页面
│       ├── components/    # 组件
│       ├── api/            # API 调用
│       └── App.tsx         # 入口
└── refs/                   # 参考项目（不在 git 内）
```