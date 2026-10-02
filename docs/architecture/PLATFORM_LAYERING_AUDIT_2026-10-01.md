# 平台分层架构审查（2026-10-01）

> 用户问："整理下我们现在接口和样式符不符合**公共的在公共组件、
> 各平台个性化的在自己的文件夹**"
>
> 本文是**代码实测**结论，不是印象 —— 每条都标了怎么查出来的。

## 一、结论速览

| 层 | 符合度 | 说明 |
|---|---|---|
| **平台客户端目录** | ✅ **符合** | 各平台有自己的文件夹，公共契约在 `base.py` |
| **每个平台内部** | ✅ **符合** | `client.py`(能力) / `apis.py`(接口常量) / `sign.py`(签名) 分工清晰 |
| **前端平台配置** | ✅ **符合** | `PLATFORM_SEARCH_CONFIG` 集中配置 |
| **前端平台分支** | ⚠️ **部分符合** | B站 30 处专属分支（**可接受**，它有独有能力） |
| **平台元数据（后端）** | ❌ **不符合** | **同一信息散落 4 个文件**，新增平台要改 4 处 |
| **平台名单硬编码** | ❌ **不符合** | `no_login = p in ("youtube","telegram")` 之类 |

---

## 二、✅ 做得对的部分（不要动）

### 2.1 目录分层正确

```
backend/app/services/platforms/
├── base.py            公共契约：BasePlatformClient + register_platform
├── types.py           公共类型：PlatformError 家族、SearchParams、SearchResult…
├── login_health.py    公共能力：resolve_connection（连接/cookie 解析）
├── session_pool.py    公共能力：会话池
├── cache.py           公共能力：缓存
├── health_routes.py   公共入口：统一体检 /platforms/{p}/health
├── bilibili/          ┐
├── douyin/            │ 各平台自己的文件夹
├── kuaishou/          │ 内含 client.py / apis.py / routes.py /
├── weibo/             │ sign.py / parser.py 等**按需**文件
├── twitter/           │
├── youtube/           │
├── telegram/          │
├── xiaohongshu/       │
└── fanqie/            ┘
```

**证据**：`ls app/services/platforms/*/`

### 2.2 每个平台内部的分工是清晰的

| 文件 | 职责 | 例 |
|---|---|---|
| `client.py` | 客户端能力（search/detail/comments…） | 所有平台都有 |
| `apis.py` | 接口路径/参数常量（**只放常量**） | 除 telegram 外都有 |
| `routes.py` | 该平台的**专属** HTTP 路由 | bili/douyin/xhs/fanqie |
| `sign.py` | 签名（抖音 a_bogus） | 只有抖音需要 |
| `parser.py` | HTML 解析（Telegram 预览页） | 只有 Telegram |
| `search_http.py` / `search_dom.py` | 双路径搜索（HTTP 优先、DOM 回退） | 只有 X |

**这个是好的** —— 平台**只写自己需要的文件**，不强行统一。

### 2.3 公共契约用基类 + 注册表

```python
@register_platform("weibo")
@register_platform("wb")        # 别名也注册
class WeiboClient(BasePlatformClient):
    ...
```

`create_client(name)` 按注册表取 —— 新增平台只需注册，不用改工厂。
**证据**：`backend/app/services/platforms/__init__.py::_auto_discover_platforms`

### 2.4 基类方法**可选实现**（不是强制）

```python
async def get_comments(...):     # 可选
    raise NotImplementedError(...)
async def get_comments_page(...):  # 可选，有默认实现（退化成 get_comments）
    ...
```

未实现的平台自动抛错 → 上层映射成 **501 + 原因**（不是返回空）。
**这个设计是对的**，且符合"不假装支持"的仓库铁律。

---

## 三、❌ 不符合的部分（真正要改的）

### 3.1 【核心问题】平台元数据散落 4 个文件

**同一个信息**（平台叫什么、要不要登录、连接名是什么）
在 **4 个地方各写了一遍**：

| 文件 | 变量 | 内容 |
|---|---|---|
| `api/v1/users.py` | `SUPPORTED` | 平台 → `{conn_key, no_login, ...}` |
| `api/v1/users.py` | `_CLIENT_ALIAS` | `xhs→xiaohongshu`, `wb→weibo`… |
| `services/platforms/health_routes.py` | `PROBE_SEARCH_TYPE` | 平台 → 探测用的搜索类型 |
| `services/platforms/health_routes.py` | （内联字典） | 平台 → **连接名**（`"xhs": "XHS"`） |
| `services/platforms/health_routes.py` | `no_login = p in (...)` | 免登录平台名单 |
| `api/v1/comments.py` | `COMMENTS_SUPPORTED` | 支持评论的平台 |
| `api/v1/comments.py` | （内联字典） | 平台 → **(连接名, cookie域名)** |
| `api/v1/comments.py` | `client_name` 逐个别名转换 | `wb→weibo`, `dy→douyin` |
| `api/v1/platform_stats.py` | `_ALIAS` | 平台别名归一 |

**后果（真实痛点）**：
新增一个平台要改 **4~5 个文件**，而且**漏一个就静默出错**：
  · 漏了 `comments.py` 的映射 → 评论接口 `KeyError`
  · 漏了 `health_routes.py` 的探测类型 → 体检拿不到结果
  · 别名忘了加 → `client_name` 找不到客户端

**这正是用户说的"不符合公共组件设计"**。

### 3.2 平台名单硬编码在公共逻辑里

```python
# health_routes.py:143
no_login = p in ("youtube", "telegram")

# comments.py:383
client_name = "bili" if p in ("bili", "bilibili") else p
if client_name == "wb": client_name = "weibo"
if client_name == "dy": client_name = "douyin"

# comments.py:399
if p in ("bili", "bilibili"):
    result = await client.get_comments_paged(...)   # B站走特殊路径
```

**问题**：这些判断**本该由平台自己声明**（"我免登录"、"我的连接名是什么"），
而不是让公共代码去记住每个平台的特征 —— 那公共代码就成了
**平台知识的垃圾场**。

### 3.3 前端 B站专属分支（⚠️ 可接受，但可收敛）

`crawler/index.tsx` 有 **30 处** `platform === 'bili'`。

**其中大部分是合理的** —— B站确实有别的平台没有的能力：
  · 弹幕 tab（`danmaku`）
  · 字幕 tab（`subtitle`）
  · 数据统计 tab（`stats`，走 B站专属 `/x/web-interface/view`）

**但有几处是不该有的**（B站被特殊对待，本可走通用路径）：
  · `platform === 'bili' ? biliConnections : searchConnections`
    —— B站有**独立的连接状态变量**（`biliConnections`/`selectedBiliConn`），
    而不是复用通用机制。这是**历史包袱**（B站是第一个做的）。
  · `if (platform === 'bili' || platform === 'wechat_mp')`
    —— 硬编码名单

---

## 四、改造方案（建议分两步）

### 第一步：收敛平台元数据（**高价值，低风险**）

建一个**单一事实来源**：每个平台在自己文件夹里声明元数据。

```python
# backend/app/services/platforms/<平台>/__init__.py 或 meta.py
PLATFORM_META = {
    "name": "weibo",
    "aliases": ["wb"],
    "conn_key": "WEIBO",         # 连接表里的平台名
    "cookie_domain": "weibo",    # netscape_to_header 用的域名
    "no_login": False,           # 免登录平台
    "probe_search_type": "note", # 体检探针用的搜索类型
    "capabilities": {            # 有哪些能力（供接口层判断）
        "comments": True,
        "replies": False,
        "self_profile": True,
    },
}
```

然后：
  · `users.SUPPORTED` → 从 meta 生成
  · `comments.COMMENTS_SUPPORTED` → 从 meta 生成
  · `health_routes` 的 3 个表 → 从 meta 生成
  · `platform_stats._ALIAS` → 从 meta 生成
  · `client_name` 转换 → 直接用 meta 的正式名

**收益**：新增平台只改**自己文件夹**（符合用户的要求），
公共文件**一行都不用动**。

**风险**：低 —— 纯重构，行为不变，有现成测试守。

### 第二步：前端平台配置（可选）

把 B站专属分支收进 `PLATFORM_SEARCH_CONFIG` 风格的配置里
（比如 `detailTabs: ['detail','danmaku','subtitle','comments','stats']`），
让 tab 渲染按配置走，而不是 30 个 if。

**收益**：中等。**风险**：中（前端改动面大，要仔细回归）。

---

## 五、我的建议

**先做第一步**（收敛后端元数据）：
  · 直接回应你的要求（公共的在公共、个性化的在自己文件夹）
  · 是纯重构，**行为不变**，风险低
  · 能让"新增平台"真的只改一个文件夹

**第二步（前端）可以缓** —— 那 30 处大部分是 B站的真实独有能力，
不是纯粹的架构问题；而且前端改大了容易引入回归。

⚠️ 但**断点续传**你说要做 —— 那个和这个重构**互不冲突**
（断点续传主要在 `download.py` 和任务表，不碰平台元数据）。
两者顺序你定：先重构再断续传，或反过来都行。
