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
- 后端：FastAPI + Python，路径 `backend/`，虚拟环境 `backend/venv/`
- 前端：React + TypeScript + Vite + AntDesign，路径 `frontend/`
- 数据库：SQLite（开发）→ PostgreSQL（规划）
- 启动：`start.bat` 同时启动后端(uvicorn)+前端(npm run dev)
- 端口：后端 8000，前端 5173

## 环境配置

### 虚拟环境
项目的 Python 虚拟环境位于：
```
F:\PycharmProjects\YLCraft\backend\venv\
```

⚠️ **重要**：所有 pip 安装和后端启动都必须使用此 venv，不要用系统 Python！

### 启动后端

**方法 1：激活 venv 后启动（推荐）**
```powershell
cd F:\PycharmProjects\YLCraft\backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

**方法 2：直接用 venv 的 python 启动**
```powershell
F:\PycharmProjects\YLCraft\backend\venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir=F:\PycharmProjects\YLCraft\backend
```

### 安装依赖
使用项目 venv 的 pip 安装：
```powershell
F:\PycharmProjects\YLCraft\backend\venv\Scripts\pip.exe install -r backend/requirements.txt
```

### 常见问题

**问题：后端启动时提示 "yt-dlp module missing"**
- **原因**：后端用系统 Python 启动，但 yt-dlp 装在 venv 里
- **解决**：确保用 venv 的 python 启动后端（见上方启动命令）

**检查当前 Python 环境**：
```powershell
# 查看当前 python 路径
(Get-Command python).Source

# 应该指向：F:\PycharmProjects\YLCraft\backend\venv\Scripts\python.exe
```

## 核心架构
- BackendManager：Provider 注册表模式，litellm 统一调用
- 三大功能：爆款拆解(Breaker) / Clip Lab / Story Maker
- 统一素材资产库(Asset Library)：视频/图片/音频/文档统一管理
- 参考项目（已 clone）：`refs/`
  - Jellyfish / ArcReel / CutClaw / NarratoAI / montage-ai / MoneyPrinterTurbo

## 当前进度（2026-05-07 更新）

**整体进度**：~100% 完成（后端 + 前端核心功能）

### 已完成模块 ✅
- ✅ Phase 1：素材资产库（Asset Library）SQLite + SQLModel
- ✅ Phase 2：素材库前端 + 后台下载任务（轮询）
- ✅ Phase 3：角色管理模块
- ✅ Phase 4：字幕提取（faster-whisper + 4 种样式）
- ✅ Phase 5：BGM 配乐（内置 10 首 + 用户上传）
- ✅ Phase 6：Live2D 工厂（立绘→绑骨→VTS 导出→口型同步）
- ✅ Phase 7：Clip Lab（CutClaw Agent / NarratoAI / MoE 多专家）
- ✅ Phase 8：爆款拆解 + Story Maker
- ✅ Phase 9：AI 图像/视频生成 + 素材采集

### 后端状态
- ✅ 核心服务 100% 完成
- ✅ 9 个 REST API 模块
- ✅ 8 个 Provider（4 LLM + 4 Image）
- ✅ 9 个社交媒体连接器

### 前端状态
- ✅ React + Vite + AntDesign 完成
- ✅ 9 个页面（素材库/下载/角色管理/剪辑/字幕/BGM/Live2D/AI 生成/素材采集）
- ✅ 字幕 + BGM 功能完整集成

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