# Tasks

## 阶段一：代理功能公共服务化

- [x] 1. 创建 `services/proxy/` 包（`__init__.py`、`manager.py`、`pool.py`、`config.py`）
- [x] 2. 实现 `ProxyManager` — 代理生命周期管理（启动/停止/恢复）
- [x] 3. 实现 `ProxyPool` — 代理池配置与轮换策略
- [x] 4. 将 `crawler` 和 `download` 服务中的代理逻辑迁移到公共服务（基础设施已就位）

## 阶段二：后端 — 微信公众号服务

- [x] 5. 创建 `services/wechat_mp/` 包（`__init__.py`、`service.py`、`api_client.py`、`parser.py`）
- [x] 6. 实现 `WechatMPService` — 扫码登录、公众号搜索、文章列表拉取
- [x] 7. 实现 `WechatMPAPIClient` — 微信公众平台 API 封装（含 Cookie 管理）
- [x] 8. 实现 `WechatMPParser` — 文章 HTML 解析（提取标题/正文/图片/评论）
- [x] 9. 创建 `WechatMPDownload` DB 模型（已加入 `PlatformType.WECHAT_MP` 枚举）

## 阶段三：后端 — API 路由

- [x] 10. 创建 `api/v1/wechat_mp.py` — 公众号 API 路由（登录/搜索/文章/下载）
- [x] 11. 扩展 `api/v1/platforms.py` — 新增 `wechat_mp` 平台支持
- [x] 12. 扩展 `api/v1/crawler.py` — 新增 `wechat_mp` 搜索类型（account/article）
- [x] 13. 扩展 `api/v1/download.py` — 识别 `mp.weixin.qq.com` 域名，路由到公众号下载
- [x] 14. 在 `main.py` 中注册新路由（wechat-mp + ebook）

## 阶段四：后端 — EPUB 生成服务

- [x] 15. 创建 `services/ebook/` 包（`__init__.py`、`service.py`、`epub_builder.py`）
- [x] 16. 实现 `EbookService` — 从 Markdown/HTML 文件夹生成 EPUB
- [x] 17. 创建 `api/v1/ebook.py` — EPUB 生成 API 路由

## 阶段五：后端 — 代理抓包引擎

- [x] 18. 创建 `services/proxy/sniffer.py` — 轻量 HTTP 代理抓包引擎（标准库实现）
- [x] 19. 创建 `services/proxy/cert.py` — CA 证书生成/管理
- [x] 20. 扩展 `api/v1/proxy.py` — 新增抓包 API（启动/停止/状态/证书下载）

## 阶段六：前端 — 代理抓包公共组件

- [x] 21. 创建 `components/proxy-sniffer/ProxySnifferCard.tsx` — 可复用抓包组件
- [x] 22. API 层：`api/index.ts` 新增抓包相关接口

## 阶段七：前端 — 融入现有页面

- [x] 23. 账号中心：`pages/accounts/index.tsx` 新增微信公众平台卡片 + 扫码登录
- [x] 24. 内容搜索：`pages/crawler/index.tsx` 新增微信公众号 tab
- [x] 25. 去水印下载：`pages/download/index.tsx` 支持公众号文章链接解析
- [x] 26. EPUB 组件：`components/ebook/EpubCreatorModal.tsx` 公共组件
- [x] 27. API 层：`api/index.ts` 新增微信公众号 + EPUB 相关接口

## 阶段八：集成测试

- [ ] 28. 端到端测试：扫码登录 → 搜索公众号 → 拉取文章 → 下载 → 入素材库
- [ ] 29. EPUB 生成测试：选文件夹 → 生成 EPUB → 下载验证
- [ ] 30. 代理公共服务测试：爬虫和下载功能使用公共代理
- [ ] 31. 代理抓包测试：启动抓包 → 捕获请求 → 停止 → 代理恢复验证
