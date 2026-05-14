# 小红书图文链接解析 → 爆款拆解

> **状态**：✅ 已实现

## 目标
为 YLCraft 爆款拆解场景添加小红书图文链接解析能力。输入小红书链接 → 提取标题/正文/图片 → 交给 LLM 分析文案结构。

## 实现状态

### 已实现文件
- `backend/app/services/xhs_parser/__init__.py` ✅
- `backend/app/services/xhs_parser/service.py` ✅
- `backend/app/connectors/social/xhs/connector.py` ✅

### 解析策略
1. `window.__INITIAL_STATE__` → JSON 解析
2. og:meta 标签兜底
3. BeautifulSoup DOM 兜底
4. 随机 UA + 请求延迟防反爬

### 集成到 breaker 流程
- `services/breaker/__init__.py` — 检测 URL 平台类型
  - 小红书图文链接 → 调用 xhs_parser → 直接进 LLM 分析
  - 视频链接（抖音/B站等）→ 原有流程（下载→转录→分析）
