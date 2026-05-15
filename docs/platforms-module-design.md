# YLCraft — 平台爬虫模块使用指南

> **版本**: v1.0
> **状态**: 基础架构完成，B站实现中
> **最后更新**: 2026-05-14

---

## 一、架构概述

### 1.1 核心设计

**支持两种模式切换**：
- **API 模式** (`api`)：直接 HTTP 请求（快速，但可能被反爬）
- **Patchright 模式** (`patchright`)：使用浏览器自动化（慢，但能绕过反爬）

**完全自主可控**：
- 不依赖外部爬虫库（如 MediaCrawler）
- 每个平台独立实现
- 参考 XHS_ALL_IN_ONE 的简洁风格

### 1.2 目录结构

```
backend/app/services/platforms/
├── __init__.py              # 工厂入口 + 便捷函数
├── base.py                  # 基础抽象类（支持模式切换）
├── types.py                 # 通用数据类型
├── utils.py                 # 通用工具（待实现）
│
├── xiaohongshu/            # 小红书（待迁移）
│   ├── __init__.py
│   ├── client.py
│   ├── search.py
│   ├── note.py
│   └── apis.py
│
├── bilibili/                # B站 ✅ 已实现
│   ├── __init__.py
│   ├── client.py           # 核心客户端
│   └── apis.py            # API 端点定义
│
├── douyin/                 # 抖音（待迁移）
├── kuaishou/               # 快手（待迁移）
├── weibo/                  # 微博（待实现）
└── zhihu/                  # 知乎（待实现）
```

---

## 二、快速开始

### 2.1 使用便捷函数（推荐）

```python
from app.services.platforms import search, get_detail

# 搜索（API 模式）
results = await search(
    platform="bili",
    keyword="鬼灭之刃",
    mode="api",
    cookie="your_cookie_here",
    max_results=20,
    search_type="note",  # "note" | "user" | "article"
)

# 搜索（Patchright 模式）
results = await search(
    platform="bili",
    keyword="鬼灭之刃",
    mode="patchright",  # 使用浏览器
    cookie="your_cookie_here",
    patchright_headless=False,  # 显示浏览器窗口
)

# 获取详情
detail = await get_detail(
    platform="bili",
    item_id="BV1xx411c7XD",
    mode="api",
    cookie="your_cookie_here",
)
```

### 2.2 使用客户端类（高级）

```python
from app.services.platforms import create_client, ClientMode
from app.services.platforms.types import ClientConfig, SearchParams, SearchType

# 创建配置
config = ClientConfig(
    platform="bili",
    mode=ClientMode.API,  # 或 ClientMode.PATCHRIGHT
    cookie="your_cookie_here",
    timeout=30,
    proxy=None,
)

# 创建客户端
client = create_client("bili", config)

# 使用客户端
async with client:
    # 搜索视频
    params = SearchParams(
        keyword="鬼灭之刃",
        max_results=20,
        search_type=SearchType.NOTE,
        extra={"order": "totalrank", "duration": 0}
    )
    results = await client.search(params)
    
    # 获取详情
    detail = await client.get_detail("BV1xx411c7XD")
    
    # B站特有：获取用户投稿
    videos = await client.get_user_videos("user_id_here")
    
    # B站特有：获取合集
    series = await client.get_series("series_id_here")
```

---

## 三、模式对比

| 特性 | API 模式 | Patchright 模式 |
|------|----------|----------------|
| **速度** | 快（直接 HTTP） | 慢（需要启动浏览器） |
| **反爬对抗** | 弱（容易被检测） | 强（真实浏览器环境） |
| **Cookie 需求** | 需要（字符串） | 需要（自动设置到浏览器） |
| **依赖** | `httpx` | `patchright` (Playwright 隐身版) |
| **适用场景** | 快速测试、低频率请求 | 生产环境、高频率请求 |

### 切换模式示例

```python
# API 模式（默认）
results = await search("bili", "keyword", mode="api")

# Patchright 模式（需要安装：pip install patchright）
results = await search("bili", "keyword", mode="patchright")
```

---

## 四、各平台功能对照

| 功能 | 小红书 | B站 | 抖音 | 快手 | 微博 | 知乎 |
|------|--------|-----|------|------|------|------|
| **搜索笔记/视频** | ✅ | ✅ | 🔄 | 🔄 | 📝 | 📝 |
| **搜索用户** | ✅ | ✅ | 🔄 | 🔄 | 📝 | 📝 |
| **获取详情** | ✅ | ✅ | 🔄 | 🔄 | 📝 | 📝 |
| **无水印资源** | ✅ | ✅ | 🔄 | 🔄 | 📝 | 📝 |
| **获取用户投稿** | ✅ | ✅ | 🔄 | 🔄 | 📝 | 📝 |
| **获取评论** | 📝 | ✅ | 🔄 | 🔄 | 📝 | 📝 |
| **B站合集** | - | ✅ | - | - | - | - |

图例：
- ✅ 已实现
- 🔄 迁移中（从旧代码迁移）
- 📝 待实现
- \- 不适用

---

## 五、从旧代码迁移

### 5.1 旧代码（mediacrawler_wrapper.py）

```python
from app.services.crawler.mediacrawler_wrapper import MediaCrawlerWrapper

wrapper = MediaCrawlerWrapper()
results = await wrapper.search_notes("xhs", "keyword", cookie)
```

### 5.2 新代码（platforms 模块）

```python
from app.services.platforms import search

results = await search(
    platform="xhs",
    keyword="keyword",
    cookie=cookie,
    mode="api",  # 或 "patchright"
)
```

### 5.3 兼容性

旧的 `MediaCrawlerWrapper` 仍然可用，但内部已改为调用新的 `platforms` 模块。

---

## 六、安装依赖

### 6.1 基础依赖（API 模式）

```bash
pip install httpx
```

### 6.2 Patchright 依赖（浏览器模式）

```bash
pip install patchright
patchright install chromium  # 安装 Chromium 浏览器
```

---

## 七、开发新平台

### 7.1 创建平台目录

```bash
mkdir -p app/services/platforms/weibo
```

### 7.2 实现客户端类

```python
# app/services/platforms/weibo/client.py
from ..base import BasePlatformClient, register_platform
from ..types import ClientConfig, SearchResult, NoteDetail

@register_platform("weibo")
class WeiboClient(BasePlatformClient):
    def __init__(self, config: ClientConfig):
        super().__init__(config)
    
    def _build_headers(self) -> dict:
        # 实现：构建请求头
        pass
    
    def _get_default_user_agent(self) -> str:
        # 实现：返回默认 User-Agent
        pass
    
    def _get_platform_domain(self) -> str:
        # 实现：返回平台域名（如 ".weibo.com"）
        pass
    
    async def search(self, params: SearchParams) -> list[SearchResult]:
        # 实现：搜索逻辑
        pass
    
    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        # 实现：获取详情逻辑
        pass
```

### 7.3 注册平台

使用 `@register_platform` 装饰器自动注册，无需手动添加。

---

## 八、调试与日志

### 8.1 日志输出

```python
import logging

# 启用调试日志
logging.getLogger("ylcraft.platforms").setLevel(logging.DEBUG)
```

### 8.2 常见错误

**错误：patchright not installed**
```bash
pip install patchright
patchright install chromium
```

**错误：Cookie 无效**
- 检查 Cookie 是否过期
- 尝试使用 Patchright 模式重新获取 Cookie

**错误：API 返回 412（预处理失败）**
- B站需要 WBI 签名，使用 Patchright 模式可以自动获取

---

## 九、TODO

- [ ] 迁移小红书（参考 XHS_ALL_IN_ONE）
- [ ] 迁移抖音
- [ ] 迁移快手
- [ ] 实现微博
- [ ] 实现知乎
- [ ] 实现 WBI 签名完整逻辑（B站）
- [ ] 添加单元测试
- [ ] 添加速率限制保护
- [ ] 支持代理池

---

## 十、参考项目

| 项目 | 用途 |
|------|------|
| **XHS_ALL_IN_ONE** | 小红书 API 调用参考 |
| **MediaCrawler** | 各平台 API 端点参考 |
| **social-auto-upload** | Patchright 使用参考 |

---

**最后更新**: 2026-05-14
**维护者**: YLCraft Team
