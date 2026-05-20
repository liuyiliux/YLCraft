# B站二维码登录实现文档

## 概述

本文档记录 YLCraft 中 B站（Bilibili）二维码扫码登录的实现细节。

## 技术参考

### API 文档来源

1. **B站官方 API 文档**：[bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)
2. **本地参考项目**：`c:\my\code\byin\bilibili-audio-downloader`

### B站 Passport API

| 接口 | 方法 | URL |
|------|------|-----|
| 生成二维码 | GET | `https://passport.bilibili.com/x/passport-login/web/qrcode/generate` |
| 轮询状态 | GET | `https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key=xxx` |

### 状态码

| code | 含义 |
|------|------|
| 86101 | 等待扫码 |
| 86090 | 已扫码，等待确认 |
| 0 | 登录成功 |
| 86038 | 二维码过期 |

## 必需请求头

B站 Passport API 需要浏览器级别的请求头才能通过校验：

```python
BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}
```

> ⚠️ 如果不携带这些 Header，会收到 `412 Precondition Failed` 错误。

## 实现文件

```
backend/app/services/cookie_acquisition/
├── platforms/
│   └── bilibili.py          # B站适配器（核心实现）
└── __init__.py              # 适配器注册
```

### 核心类

```python
class BilibiliQrcodeAdapter(QrcodeAdapter):
    async def generate_qrcode(self) -> dict:
        """生成二维码，返回 base64 图片 + qrcode_key"""
        
    async def check_status(self, session_key: str) -> dict:
        """轮询扫码状态，返回 waiting/scanned/confirmed/expired"""
```

### 注册到适配器注册表

在 `platforms/__init__.py` 中注册：

```python
_qrcode_registry: dict[str, str] = {
    "bilibili": "app.services.cookie_acquisition.platforms.bilibili:BilibiliQrcodeAdapter",
}
```

## 前端集成

### WebSocket 连接

开发环境下 WebSocket 直连后端 8000 端口：

```typescript
const connectWebSocket = (sid: string) => {
  const isDev = import.meta.env.DEV
  const wsUrl = isDev
    ? `ws://${window.location.hostname}:8000/api/v1/platforms/acquire/qrcode/${sid}/ws`
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws://'}${window.location.host}/api/v1/platforms/acquire/qrcode/${sid}/ws`
  const ws = new WebSocket(wsUrl)
}
```

> ⚠️ Vite 代理的 WebSocket 转发有时不可靠，所以开发环境直接连接后端。

### API 调用

```typescript
import { qrcodeGenerate, getQrcodeStatus, refreshQrcode } from '@/api'

// 生成二维码
const res = await qrcodeGenerate({ platform: 'bilibili' })

// 监听状态变化
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  if (msg.type === 'completed' && msg.status === 'success') {
    // 登录成功
  }
}
```

## 已知问题

### 1. Vite WebSocket 代理不稳定

**问题**：Vite 配置了 `ws: true`，但浏览器连接 Vite 服务器后再转发 WebSocket 到后端时，可能会失败。

**解决**：开发环境 WebSocket 直连 `ws://localhost:8000`，绕过 Vite 代理。

### 2. B站 API 返回 412

**问题**：请求头不完整，B站风控拦截。

**解决**：添加 `User-Agent`、`Referer`、`Origin` 请求头。

### 3. B站 API 返回 405

**问题**：请求方法错误。

**解决**：两个接口都是 **GET** 请求，不是 POST。

## 生产环境部署

### Nginx 配置

如果使用 Nginx 反向代理，需要开启 WebSocket 支持：

```nginx
location /api/v1/platforms/acquire {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

### 检查项

1. ✅ 后端 8000 端口正常
2. ✅ Nginx/反向代理配置了 WebSocket 升级头
3. ✅ 前端 WebSocket 路径使用正确的 `/platforms` 前缀
4. ✅ CORS 配置允许 WebSocket 连接
