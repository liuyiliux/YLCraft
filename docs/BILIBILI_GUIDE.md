# YLCraft × B站 完整功能指南

> **创建时间**：2026-05-20  
> **参考项目**：BiliTools、MediaCrawler、bilibili-api-python  
> **法律声明**：本文档仅提供功能思路和技术方案，不涉及任何代码复制。

---

## 一、已实现功能

### 1.1 B站二维码登录 ✅

**实现文件**：
- 后端：`backend/app/services/cookie_acquisition/platforms/bilibili.py`
- 前端：`frontend/src/pages/accounts/index.tsx`（QrLoginPanel）

**API 端点**：
| 接口 | 方法 | URL |
|------|------|-----|
| 生成二维码 | POST | `/api/v1/platforms/acquire/qrcode/generate` |
| WebSocket 推送 | WS | `/api/v1/platforms/acquire/qrcode/{sid}/ws` |
| 轮询状态 | GET | `/api/v1/platforms/acquire/qrcode/{sid}/status` |

**B站 Passport API**：
| 接口 | 方法 | URL |
|------|------|-----|
| 生成二维码 | GET | `https://passport.bilibili.com/x/passport-login/web/qrcode/generate` |
| 轮询状态 | GET | `https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key=xxx` |

**状态码**：
| code | 含义 |
|------|------|
| 86101 | 等待扫码 |
| 86090 | 已扫码，等待确认 |
| 0 | 登录成功 |
| 86038 | 二维码过期 |

**必需请求头**（否则 412 Precondition Failed）：
```python
BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}
```

**已知问题**：
1. Vite WebSocket 代理不稳定 → 开发环境直连后端 8000 端口
2. B站 API 返回 412 → 检查请求头是否完整
3. B站 API 返回 405 → 确认使用 GET 而非 POST

**Nginx 配置**（生产环境）：
```nginx
location /api/v1/platforms/acquire {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

---

### 1.2 字幕下载 ✅

**实现文件**：`backend/app/services/subtitle/service.py`

**功能**：
- B站字幕下载（SRT/ASS/VTT 格式）
- 字幕样式编辑
- 字幕烧录到视频
- 多语言字幕支持

---

### 1.3 弹幕下载 ✅

**实现文件**：
- 后端：`backend/app/services/platforms/bilibili/client.py` → `get_danmaku()`
- 前端：`frontend/src/components/bilibili/VideoDetailDrawer.tsx`
- API：`/api/v1/bilibili/danmaku`

**功能**：
- 获取视频弹幕列表（XML 格式解析）
- 弹幕数据展示（时间、类型、内容、发送者）
- 弹幕文件下载（JSON/ASS/XML 格式）
- 弹幕类型支持：滚动（1）、底部（4）、顶部（5）

**弹幕数据结构**：
```python
{
    "time": 12.3,        # 出现时间（秒）
    "type": 1,           # 弹幕类型
    "font_size": 25,      # 字号
    "color": 16777215,    # 颜色（十进制）
    "timestamp": 1234567,  # 发送时间戳
    "pool": 0,            # 弹幕池
    "user_id": "abc123",  # 发送者 mid hash
    "dmid": "12345",      # 弹幕 ID
    "text": "弹幕内容"     # 弹幕文本
}
```

> ⚠️ **注意**：当前弹幕通过 REST API（`/x/v1/dm/list.so`）获取，非 gRPC 方式。可升级为 gRPC 方式获取历史弹幕。

---

### 1.4 视频下载（普通清晰度）✅

**实现文件**：`backend/app/services/platforms/bilibili/client.py`

**功能**：
- 普通清晰度视频下载（MP4 格式）
- 通过 `/x/player/playurl` 获取播放地址

> ⚠️ **当前限制**：不支持 4K/8K/HDR/杜比视界高清格式，见第三章 P0 优化项。

---

### 1.5 评论获取 ✅

**实现文件**：
- 后端：`backend/app/services/platforms/bilibili/routes.py`（API 路由）
- 后端：`backend/app/services/platforms/bilibili/client.py` → `get_comments_paged()`
- 前端：`frontend/src/components/bilibili/VideoDetailDrawer.tsx`

**API 端点**：
| 接口 | 方法 | URL |
|------|------|-----|
| 获取评论 | GET | `/api/v1/bilibili/comments` |
| 发送评论 | POST | `/api/v1/bilibili/comment/send` |

**请求参数**（GET `/comments`）：
| 参数 | 类型 | 说明 |
|------|------|------|
| `bvid` | string | 视频 BV 号（必填） |
| `page` | int | 页码，从 1 开始（默认 1） |
| `page_size` | int | 每页条数，默认 20，最大 50 |
| `sort` | int | 排序方式（见下表） |
| `offset` | string | 游标偏移值，用于加载更多 |
| `conn_id` | string | 平台连接 ID（可选） |

**排序映射**（`sort` → B站 `mode`）：
| 前端 sort 值 | 后端 mode | 排序名称 | 分页方式 |
|-------------|-----------|----------|----------|
| 0 | 3 | 最热（热门评论） | WBI API + `pagination_str` 游标 |
| 1 | 2 | 最新（最新评论） | WBI API + `pagination_str` 游标 |
| 2 | 1 | 最早 | 非 WBI 旧版 API + `pn` 页码 |

**⚠️ 重要坑点：WBI API 与最早排序不兼容**

B站 WBI 评论 API（`/x/v2/reply/wbi/main`）对 `mode=1`（最早）排序时，`pagination_reply.next_offset` 游标在时间排序下不可靠，会导致"加载更多返回重复评论"的 bug。

**解决方案**：
- `mode=1`（最早）→ 改用非 WBI 旧版 API `/x/v2/reply/main`，用 `pn` 页码分页
- `mode=2/3`（最新/最热）→ 保持 WBI API + `pagination_str` 游标分页

**⚠️ 另一个坑点：`next_offset` 的正确提取路径**

B站 API 返回的游标结构：
```json
"cursor": {
  "pagination_reply": { "next_offset": "CAESEDE4..." },  // WBI API 的 offset 在这里
  "is_end": false,
  "all_count": 150
}
```

**错误做法**：`cursor.get("next_offset")` —— 直接从 cursor 取，会得到空字符串 `""`
**正确做法**：`cursor.get("pagination_reply", {}).get("next_offset", "")` —— 从 `pagination_reply` 中取

> 这个 bug 会导致所有分页请求都使用空的 `offset`，API 始终返回第一页，造成评论重复加载。**（已修复）**

**评论数据结构**（返回值示例）：
```python
{
    "total": 150,           # 评论总数
    "page": 1,              # 当前页码
    "page_size": 20,        # 每页条数
    "comments": [
        {
            "rpid": 1234567890,       # 评论 ID
            "user_name": "用户名",    # 评论者昵称
            "user_avatar": "https://...",  # 头像 URL
            "mid": "123456",          # 用户 mid
            "message": "评论内容",    # 评论文本
            "like_count": 100,        # 点赞数
            "ctime": 1716000000,      # 发布时间（Unix 时间戳）
            "replies_count": 5,       # 回复数（子评论数）
        }
    ],
    "next_offset": "CAESEDE4...",  # 下一页游标（最早排序时为空）
    "has_more": true               # 是否还有更多
}
```

---

## 二、B站 API 调用方式分析

### 2.1 登录认证

| API 端点 | 用途 | YLCraft 现状 |
|-----------|------|--------------|
| `/x/passport-login/web/qrcode/poll` | 二维码登录轮询 | ✅ 已实现 |
| `/x/passport-login/web/login` | 密码/短信登录 | ❌ 未实现 |
| `/x/passport-login/web/cookie/refresh` | Cookie 刷新 | ❌ 未实现 |
| `bpapis/bilibili.api.ticket.v1.Ticket/GenWebTicket` | 获取 API 签名票据 | ❌ 未实现 |
| `/x/frontend/finger/spi` | 获取 buvid3/buvid4 | ❌ 未实现 |

**关键发现**（来自 BiliTools 分析）：
- BiliTools 使用 **HMAC-SHA256** 对请求签名（`XgwSnGZ1p` 为 key）
- 需要 `bili_ticket` + `buvid3` + `buvid4` + `_uuid` 等 Cookie 才能调用高阶 API
- Cookie 刷新需要 `refresh_token`（存在 Cookie 中）

---

### 2.2 弹幕获取（已实现 ✅，可优化）

**YLCraft 当前实现**：
- 通过 REST API（`/x/v1/dm/list.so`）获取弹幕 XML
- 解析为结构化数据，支持 JSON/ASS/XML 格式下载
- 实现文件：`backend/app/services/platforms/bilibili/client.py` → `get_danmaku()`

**可优化方向**（参考 BiliTools 的 gRPC 方式）：
- gRPC 方式可获取**历史弹幕**（更早的弹幕数据）
- gRPC 方式更稳定，不易被 B站 反爬限制

| 项目 | 实现方式 | 说明 |
|------|-----------|------|
| **BiliTools** | gRPC + Protobuf | 使用 `dm.v1.Dm` 服务，protobuf 编码 |
| **YLCraft（当前）** | ✅ REST API | 已能下载弹幕，方式简单但功能完整 |

**Proto 定义来源**（如要升级为 gRPC 方式）：  
`https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/grpc_api/bilibili/tv/interfaces/dm/v1/dm.proto`

---

### 2.3 视频信息获取 API

| API 端点 | 用途 | 返回关键字段 |
|-----------|------|-------------|
| `/x/web-interface/view` | 获取视频详情 | `pages[].cid`，`cid` 是获取弹幕的关键参数 |
| `/x/player/wbi/playurl` | 获取播放/下载 URL（高清需用此端点） | `dash`（DASH 格式，含 4K/8K/HDR 链接）|
| `/pgc/view/web/season` | 番剧/影视详情 | 分集信息、付费状态 |

**关键发现**：
- 高清视频（4K/8K/HDR）需要通过 `wbi/playurl` 端点获取 DASH 链接
- 该端点需要 **WBI 签名**（B站的反爬机制）
- YLCraft 当前仅支持普通 MP4 格式，不支持 DASH 高清格式

---

## 三、优化清单（按优先级排序）

> ✅ 表示已实现，📋 表示部分实现，❌ 表示未实现

### 🔴 P0 — 必须实现

#### 1. 高清视频下载（DASH 格式）🔥

**当前状态**：❌ 不支持 4K/8K/HDR/杜比视界

**功能描述**：
- 支持 4K/8K/HDR/杜比视界高清格式
- 使用 DASH 格式（分段下载，支持自适应码率）
- 音频视频分离下载，然后合并

**技术实现**：
1. 调用 `/x/player/wbi/playurl` 获取 DASH URL（需要 WBI 签名）
2. 解析 DASH XML，提取最高清晰度视频/音频 URL
3. 使用 `yt-dlp` 或 `aria2c` 多线程下载
4. 使用 FFmpeg 合并视频和音频

**WBI 签名**：YLCraft 已有实现（`services/platforms/bilibili/client.py` → `BilibiliSign` 类），可直接使用。

**参考代码位置**（BiliTools）：
- `src-tauri/src/services/aria2c.rs`（下载实现）
- `src/services/media/index.ts`（获取视频信息）

**业务价值**：⭐⭐⭐⭐⭐（用户刚需，高清是核心竞争力）

---

#### 2. Cookie 刷新机制

**当前状态**：❌ 未实现

**功能描述**：
- 自动刷新过期的 Cookie
- 使用 `refresh_token` 获取新 Cookie
- 避免用户频繁重新扫码登录

**API 端点**：
```
POST https://passport.bilibili.com/x/passport-login/web/cookie/refresh
POST https://passport.bilibili.com/x/passport-login/web/confirm/refresh
```

**参考代码位置**（BiliTools）：
- `src-tauri/src/services/login.rs` → `refresh_cookie()`

**业务价值**：⭐⭐⭐⭐（登录态持久化，用户体验）

---

### 🟠 P1 — 强烈推荐

#### 3. 密码/短信登录

**当前状态**：❌ 未实现（仅支持二维码登录）

**功能描述**：
- 支持账号密码登录
- 支持短信验证码登录

**API 端点**：
```
POST https://passport.bilibili.com/x/passport-login/web/login
POST https://passport.bilibili.com/x/passport-login/web/login/sms
```

**参考代码位置**（BiliTools）：
- `src-tauri/src/services/login.rs` → `pwd_login()`, `sms_login()`

**业务价值**：⭐⭐⭐（多登录方式，方便桌面端用户）

---

#### 4. 无损音频下载

**当前状态**：❌ 未实现

**功能描述**：
- 下载 B站音乐区的无损音频（FLAC/320Kbps）
- 支持歌单批量下载

**API 端点**：
```
https://www.bilibili.com/audio/music-service-c/web/song/info
```

**参考代码位置**（BiliTools）：
- `src/services/media/index.ts` → `Music` 类型处理

**业务价值**：⭐⭐⭐⭐（音乐创作者需求）

---

#### 5. 用户内容批量下载

**当前状态**：📋 视频下载已支持，批量功能未完善

**功能描述**：
- 批量下载 UP主的所有投稿视频
- 批量下载收藏夹内容
- 批量下载"稍后再看"列表

**API 端点**：
```
https://api.bilibili.com/x/polymer/web-space/home/seasons_series  # 用户投稿
https://api.bilibili.com/x/v3/fav/folder/created/list-all        # 收藏夹
https://api.bilibili.com/x/v2/history/toview/web                   # 稍后再看
```

**参考代码位置**（BiliTools）：
- `src/components/DownPage/` (UI)
- `src/services/media/data.ts` (`UserVideo`, `WatchLater`, `Favorite` 类型）

**业务价值**：⭐⭐⭐（内容采集自动化）

---

### 🟡 P2 — 推荐

#### 6. 下载历史记录

**当前状态**：❌ 未实现

**功能描述**：
- 保存下载记录到本地数据库
- 支持重新下载、查看历史

**技术实现**：
- 使用 SQLite 存储下载历史
- 参考 BiliTools 的 `storage.rs`

**业务价值**：⭐⭐⭐（用户体验）

---

#### 7. 剪辑板监听

**当前状态**：❌ 未实现

**功能描述**：
- 自动识别剪辑板中的 B站链接
- 弹出下载提示

**技术实现**：
- 使用 Tauri 的 `tauri-plugin-clipboard-manager`
- 或者：使用 Electron 的 `clipboard` API

**参考代码位置**（BiliTools）：
- `src/services/clipboard.ts`

**业务价值**：⭐⭐⭐⭐（效率提升）

---

### 🟢 P3 — 可选

#### 8. AI 总结（B站官方 AI 助手）

**当前状态**：❌ 未实现

**功能描述**：
- 获取 B站官方 AI 助手对视频的总结
- 生成 Markdown 格式的内容总结

**业务价值**：⭐⭐（AI 特色功能）

---

#### 9. NFO 刮削文件生成

**当前状态**：❌ 未实现

**功能描述**：
- 为下载的视频生成 NFO 文件（Kodi/Emby/Plex 兼容）
- 包含视频元数据（标题、简介、演员、导演等）

**技术实现**：
- 使用 XML 格式生成 NFO 文件

**参考代码位置**（BiliTools）：
- `src-tauri/src/services/ffmpeg.rs`

**业务价值**：⭐⭐（影音管理工具用户）

---

## 四、技术实现指南

### 4.1 高清视频下载（WBI 签名 + DASH）

**YLCraft 已有 WBI 签名实现**（`services/platforms/bilibili/client.py` → `BilibiliSign` 类）：

```python
# 已实现的 WBI 签名工具
class BilibiliSign:
    def __init__(self, img_key: str, sub_key: str):
        self.img_key = img_key
        self.sub_key = sub_key
    
    def get_mixin_key(self, orig: str) -> str:
        """对原始 key 进行混淆加密"""
        MIXIN_KEY_ENC_TAB = [...]  # 已定义
        return ''.join([orig[i] for i in MIXIN_KEY_ENC_TAB])[:32]
    
    def sign(self, params: Dict[str, Any]) -> str:
        """对参数进行 WBI 签名"""
        # ... 已实现
```

**高清视频下载步骤**：
1. 调用 `_get_wbi_keys()` 获取 img_key + sub_key（已有实现）
2. 使用 `BilibiliSign().sign(params)` 对参数签名（已有实现）
3. 调用 `/x/player/wbi/playurl?vid=...&wts=...&w_rid=...` 获取 DASH URL（需实现）
4. 解析 DASH XML，提取最高清晰度视频/音频 URL（需实现）
5. 使用 `yt-dlp` 或 `aria2c` 多线程下载（需实现）
6. 使用 FFmpeg 合并视频和音频（已有实现）

**参考**：
- WBI 签名算法文档：`https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign-wbi.md`
- DASH 格式解析：ISO 23009-1 标准

---

### 4.2 Cookie 刷新

**步骤**：
1. 从 Cookie 中读取 `refresh_token`
2. 调用 `/x/passport-login/web/cookie/refresh`
3. 解析响应，提取新 Cookie
4. 调用 `/x/passport-login/web/confirm/refresh` 确认
5. 更新本地 Cookie 存储

**参考代码**（Rust → Python 翻译）：
```python
async def refresh_cookie(refresh_token: str, csrf: str):
    url = "https://passport.bilibili.com/x/passport-login/web/cookie/refresh"
    params = {
        "csrf": csrf,
        "refresh_csrf": csrf,
        "refresh_token": refresh_token,
        "source": "main_web",
    }
    response = await httpx.AsyncClient().post(url, params=params)
    # 解析 Set-Cookie Header，更新 Cookie
    new_cookies = response.headers.get_list("Set-Cookie")
    return new_cookies
```

---

### 4.3 弹幕获取（gRPC 方式，可选升级）

当前 YLCraft 使用 REST API 获取弹幕，如需升级为 gRPC 方式（获取历史弹幕）：

**步骤**：
1. 从 `SocialSisterYi/bilibili-API-collect` 获取 `dm.proto` 定义
2. 使用 `protoc` 或 `protobufjs` 生成 Python/TypeScript 代码
3. 调用 B站 gRPC 服务（需要 Cookie 认证）
4. 解析 protobuf 二进制数据为弹幕对象

**注意**：B站 gRPC 服务可能需要特殊的认证 Header（如 `authorization`），需要抓包分析。

---

## 五、法律合规性声明

### 5.1 GPL-3.0 协议约束

BiliTools 使用 **GPL-3.0-or-later** 协议，这意味着：
1. ❌ **禁止直接复制代码**：如果复制超过 10 行代码，YLCraft 可能被 "GPL 感染"，需要开源
2. ✅ **允许参考功能思路**：可以研究 BiliTools 的功能，然后自己重新实现
3. ✅ **允许研究 API 端点**：B站 API 是公开的（虽然未官方文档化），可以调用相同的 API

### 5.2 正确的实现方式

1. **研究 BiliTools 的功能**（已完成 ✅）
2. **自己重新编写代码**（不要复制粘贴）
3. **参考 API 端点**（调用相同的 B站 API 是允许的）
4. **不要分发 BiliTools 的修改版本**（除非你也开源）

---

## 六、参考资料

### 6.1 BiliTools 代码位置

| 功能 | 文件路径 |
|------|----------|
| 登录（Rust） | `src-tauri/src/services/login.rs` |
| 下载（Rust） | `src-tauri/src/services/aria2c.rs` |
| 弹幕（TypeScript） | `src/services/media/dm.ts` |
| 视频信息（TypeScript） | `src/services/media/data.ts` |
| 队列管理（Rust） | `src-tauri/src/services/queue/` |

### 6.2 B站 API 参考资料

| 资源 | 链接 |
|------|------|
| B站 API 收集 | https://github.com/SocialSisterYi/bilibili-API-collect |
| bilibili-api-python | https://github.com/Nemo2011/bilibili-api |
| MediaCrawler | https://github.com/NanmiCoder/MediaCrawler |

---

**维护者**：YLCraft Team  
**最后更新**：2026-05-21
