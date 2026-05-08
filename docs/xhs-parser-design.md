# 小红书图文链接解析 → 爆款拆解

## 目标
为 YLCraft 爆款拆解场景添加小红书图文链接解析能力。输入小红书链接 → 提取标题/正文/图片 → 交给 LLM 分析文案结构。

## 参考实现
- yiliu `backend/src/services/xiaohongshu_service.py` — 核心解析逻辑
- 核心策略：从 `window.__INITIAL_STATE__` 提取 JSON，含 `note.noteDetailMap` → `imageList`

## 实现方案

### 1. 新增服务 `services/xhs_parser/`
- `service.py` — XhsParserService
  - `parse(url)` → 返回 `{title, description, images, author, likes}`
  - 策略1: `window.__INITIAL_STATE__` → JSON 解析
  - 策略2: og:meta 标签兜底
  - 策略3: BeautifulSoup DOM 兜底
  - 随机 UA + 请求延迟防反爬

### 2. 集成到 breaker 流程
- `services/breaker/__init__.py` — 检测 URL 平台类型
  - 小红书图文链接 → 调用 xhs_parser → 直接进 LLM 分析
  - 视频链接（抖音/B站等）→ 原有流程（下载→转录→分析）

### 3. 前端
- `pages/breaker/index.tsx` — 输入框支持小红书链接
- 显示解析结果（标题+图片预览）→ 确认后触发 LLM 分析

## 关键文件
- 新建：`backend/app/services/xhs_parser/__init__.py`
- 新建：`backend/app/services/xhs_parser/service.py`
- 修改：`backend/app/services/breaker/__init__.py`
- 修改：`frontend/src/pages/breaker/index.tsx`
