# Design: 微信公众号文章下载

## 借鉴 EasyWechatDownload 的核心思路

EasyWechatDownload v1.1.5 新增"公众号平台模式"，不依赖本地代理抓包，直接调用微信公众平台接口：

1. 扫码登录微信公众平台 → 获取 session cookie
2. 搜索公众号（名称 → FakeID）
3. 翻页拉取历史文章列表（含标题/链接/封面/摘要/时间）
4. 勾选文章批量下载

代理模式稳定性差（作者自评"看运气"），所以 YLCraft 直接借鉴平台模式。

---

## 架构流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端页面                                   │
│                                                                   │
│  账号中心               内容搜索              去水印下载           │
│  /accounts             /crawler              /download            │
│  ┌──────────┐          ┌──────────┐          ┌──────────┐        │
│  │ 微信公众  │          │ 微信公众  │          │ 粘贴文章  │        │
│  │ 平台卡片  │          │ 号 tab   │          │ 链接     │        │
│  │ 扫码登录  │          │          │          │ 解析下载  │        │
│  └────┬─────┘          └────┬─────┘          └────┬─────┘        │
│       │                     │                     │               │
│       │              ┌──────┴──────┐              │               │
│       │              │ 搜索公众号   │              │               │
│       │              │ 拉取文章列表 │              │               │
│       │              │ 勾选 → 下载  │              │               │
│       │              │ 勾选 → 入库  │              │               │
│       │              └──────┬──────┘              │               │
│       │                     │                     │               │
│       │              ┌──────┴──────┐              │               │
│       │              │ EPUB 公共   │◄─────────────┤               │
│       │              │ 组件        │  素材库中也   │               │
│       │              │ 选文件夹 →  │  可调用       │               │
│       │              │ 生成 EPUB   │              │               │
│       │              └─────────────┘              │               │
└───────┼─────────────────────┼─────────────────────┼───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      后端 API 层                                  │
│                                                                   │
│  /api/v1/platforms     /api/v1/crawler      /api/v1/download     │
│  (已有, 扩展平台)       (已有, 扩展搜索)      (已有, 扩展解析)     │
│                                                                   │
│  /api/v1/wechat-mp              /api/v1/ebook                     │
│  (新增)                          (新增)                            │
│  POST /login/qrcode             POST /generate                    │
│  GET  /login/status             GET  /tasks/{id}                  │
│  GET  /search-accounts                                           │
│  GET  /articles                                                   │
│  POST /download-articles                                          │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      服务层                                        │
│                                                                   │
│  services/wechat_mp/           services/proxy/                    │
│  ├── service.py                ├── __init__.py                    │
│  ├── api_client.py             ├── manager.py                     │
│  └── parser.py                 └── pool.py                        │
│                                                                   │
│  services/ebook/               (复用现有)                          │
│  ├── __init__.py               services/asset/service.py          │
│  ├── service.py                services/download/manager.py       │
│  └── epub_builder.py           services/crawler/service.py        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 数据库模型

### 新增 `wechat_mp_downloads` 表

```python
class WechatMPDownload(SQLModel, table=True):
    __tablename__ = "wechat_mp_downloads"
    id: str = Field(default_factory=uuid4_str, primary_key=True)
    conn_id: str        # 关联 platform_connections.id
    account_name: str   # 公众号名称
    fake_id: str        # 公众号 FakeID
    article_title: str  # 文章标题
    article_url: str    # 文章链接
    content_url: str    # 微信 content_url
    cover_url: str      # 封面图
    digest: str         # 摘要
    publish_time: datetime
    status: str = "pending"  # pending/downloading/done/failed
    format: str = "md"       # md/html/pdf
    file_path: str           # 本地文件路径
    asset_id: str            # 关联素材库 asset
    error_message: str
    created_at: datetime
```

### 平台连接扩展

`platform_connections` 表已支持 `platform` 字段存储任意平台标识，新增 `wechat_mp` 平台类型：
- `auth_type`: `qrcode`（微信公众平台扫码登录）
- `credentials`: `{ "token": "...", "cookie": "...", "fake_id": "..." }`

---

## API 设计

### 1. 微信公众号 API（`/api/v1/wechat-mp`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/login/qrcode` | 生成登录二维码，返回 `{ qr_url, session_id }` |
| `GET` | `/login/status/{session_id}` | 轮询登录状态 |
| `GET` | `/search-accounts` | 搜索公众号 `?keyword=xxx&conn_id=xxx` |
| `GET` | `/articles` | 拉取文章列表 `?conn_id=xxx&fake_id=xxx&page=1&page_size=20` |
| `POST` | `/download-articles` | 批量下载文章 `{ conn_id, article_ids[], format }` |
| `POST` | `/download-single` | 下载单篇文章 `{ conn_id, article_url, format }` |
| `GET` | `/download/tasks/{task_id}` | 查询下载任务状态 |
| `POST` | `/import-assets` | 将已下载文章导入素材库 |

### 2. EPUB API（`/api/v1/ebook`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/generate` | 从文章文件夹生成 EPUB `{ title, folder_path, cover_url?, author? }` |
| `GET` | `/tasks/{task_id}` | 查询生成任务状态 |

### 3. 扩展已有 API

**`/api/v1/platforms/supported`** — 新增 `wechat_mp` 平台：
```json
{ "value": "wechat_mp", "label": "微信公众号", "auth_types": ["qrcode"], "support_qrcode": true }
```

**`/api/v1/crawler/search-enhanced`** — 新增 `platform: "wechat_mp"`，`search_type: "account"|"article"`。

**`/api/v1/download/parse`** — 新增微信公众号文章 URL 解析（`mp.weixin.qq.com` 域名检测）。

---

## 前端设计

### 账号中心 — 新增微信公众平台卡片

在 `PLATFORM_METAS` 数组中新增：
```tsx
{ value: 'wechat_mp', label: '微信公众号', icon: <WechatOutlined />, 
  color: '#07C160', authTypes: ['qrcode'], supportQrcode: true }
```

复用已有的扫码登录流程（`qrcodeGenerate` / `getQrcodeStatus`）。

### 内容搜索 — 新增微信公众号 Tab

在 `PLATFORMS` 数组中新增 `wechat_mp`，搜索类型为：
- **搜索公众号**（`search_type: "account"`）：输入关键词 → 展示公众号列表（名称/微信号/简介）
- **拉取文章列表**（`search_type: "article"`）：点击公众号 → 翻页展示文章列表（标题/封面/摘要/时间）
- 勾选文章 → 下载 或 导入素材库

### 去水印下载 — 支持公众号文章链接

扩展 URL 检测逻辑，识别 `mp.weixin.qq.com` 域名，调用 `wechat_mp/download-single` 下载。

### EPUB 公共组件

`frontend/src/components/ebook/EpubCreatorModal.tsx`：
- Props: `open`, `onClose`, `defaultFolder?`, `defaultTitle?`
- 交互：选文件夹 → 填书名/作者/封面 → 开始生成 → 进度展示 → 下载 EPUB
- 调用位置：素材库详情抽屉、下载完成弹窗

---

## 代理功能公共服务化

将代理相关逻辑从各处抽成 `services/proxy/` 公共服务：

```
services/proxy/
├── __init__.py        # 导出 get_proxy_manager
├── manager.py         # ProxyManager — 代理生命周期管理
├── pool.py            # ProxyPool — 代理池/轮换策略
└── config.py          # 代理配置模型
```

已有 `app/api/v1/proxy.py`（图片防盗链代理）不受影响，继续作为独立路由存在。
新的代理公共服务供 `crawler`、`download` 等服务模块通过 `get_proxy_manager()` 调用。

---

## 代理抓包公共组件

借鉴 EasyWechatDownload 的代理抓包模式，新增一个**可复用的代理抓包公共组件**，供前端各页面按需嵌入。

### 组件设计

`frontend/src/components/proxy-sniffer/ProxySnifferCard.tsx`：

```
Props:
  open: boolean                    # 是否显示
  onClose: () => void              # 关闭回调
  targetDescription?: string       # 抓包目标描述，如 "微信文章请求"
  proxyHost?: string               # 代理地址，默认 127.0.0.1
  proxyPort?: number               # 代理端口，默认 8080
  listenDuration?: number          # 监听时长（秒），默认 60
  onCapture: (requests: CapturedRequest[]) => void  # 抓到请求的回调
  onError?: (error: string) => void
```

**交互流程**（参考 EasyWechatDownload 的监控下载模式）：

```
用户点击「开始抓包」
  → 启动本地 HTTP/HTTPS 代理
  → 倒计时（如 60 秒）
  → 用户在目标应用中操作（如电脑版微信打开公众号文章）
  → 代理拦截匹配的请求（域名/URL 模式过滤）
  → 实时展示捕获到的请求列表
  → 倒计时结束或用户手动停止
  → 自动恢复系统代理设置
  → 回调 onCapture 返回捕获列表
```

### 核心功能

| 功能 | 说明 |
|------|------|
| **代理启停** | 一键启动/停止本地 HTTP/HTTPS 代理，自动保存/恢复系统代理 |
| **证书管理** | 首次使用引导安装 CA 证书（HTTPS 抓包需要） |
| **域名过滤** | 按目标域名/URL 模式过滤，只捕获感兴趣请求 |
| **实时展示** | 倒计时进度条 + 捕获请求列表（URL / 方法 / 状态码 / 时间） |
| **请求详情** | 点击展开查看请求头、响应体（JSON/HTML 格式化） |
| **代理恢复** | 关闭时自动恢复系统代理，防止断网（借鉴 EasyWechatDownload 1.0.15 修复经验） |
| **状态持久化** | 异常退出后重启可检测并恢复代理状态 |

### 后端配套

新增 `services/proxy/sniffer.py` — 抓包引擎：

```
services/proxy/
├── __init__.py        # 导出 get_proxy_manager, get_sniffer
├── manager.py         # ProxyManager — 代理生命周期管理
├── pool.py            # ProxyPool — 代理池/轮换策略
├── config.py          # 代理配置模型
├── sniffer.py         # ProxySniffer — 抓包引擎（mitmproxy/mitm 集成）
└── cert.py            # CertManager — CA 证书生成/管理
```

### API 扩展（`/api/v1/proxy`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/sniffer/start` | 启动抓包代理 `{ port?, filter_domains?[], duration? }` → `{ session_id }` |
| `GET` | `/sniffer/status/{session_id}` | 查询抓包状态 + 已捕获请求列表 |
| `POST` | `/sniffer/stop/{session_id}` | 手动停止抓包 |
| `GET` | `/sniffer/cert` | 下载 CA 证书（首次安装用） |
| `GET` | `/sniffer/health` | 检查系统代理状态 |

### 使用场景

| 场景 | 嵌入位置 | 说明 |
|------|---------|------|
| 公众号文章抓包 | 内容搜索 → 微信公众号 tab | 备选方案，平台模式不稳定时启用 |
| 抖音/小红书数据抓包 | 内容搜索 → 各平台 tab | 需要登录态但无平台 API 时的备选 |
| 通用 HTTP 调试 | 设置页 / 开发者工具 | 查看应用网络请求 |
| 批量下载备选 | 去水印下载页 | 代理模式作为平台 API 的降级方案 |
