# YLCraft 开发环境配置

## 虚拟环境位置

项目的 Python 虚拟环境位于：
```
F:\PycharmProjects\YLCraft\backend\venv\
```

⚠️ **重要**：所有 pip 安装和后端启动都必须使用此 venv，不要用系统 Python！

## 正确启动后端

### 方法 1：激活 venv 后启动（推荐）
```powershell
cd F:\PycharmProjects\YLCraft\backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

### 方法 2：直接用 venv 的 python 启动
```powershell
F:\PycharmProjects\YLCraft\backend\venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir=F:\PycharmProjects\YLCraft\backend
```

## 安装依赖

使用项目 venv 的 pip 安装：
```powershell
F:\PycharmProjects\YLCraft\backend\venv\Scripts\pip.exe install -r backend/requirements.txt
```

## 常见问题

### 问题：后端启动时提示 "yt-dlp module missing"
**原因**：后端用系统 Python 启动，但 yt-dlp 装在 venv 里。

**解决**：确保用 venv 的 python 启动后端（见上方启动命令）。

### 检查当前 Python 环境
```powershell
# 查看当前 python 路径
(Get-Command python).Source

# 应该指向：F:\PycharmProjects\YLCraft\backend\venv\Scripts\python.exe
```

## 技术栈参考
- 后端框架：FastAPI
- 虚拟环境：Python venv（位于 backend/venv/）
- 包管理：pip（使用 venv 内的 pip.exe）
- 后端启动：uvicorn
