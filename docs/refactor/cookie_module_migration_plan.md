# Cookie 模块重构计划

## 目标
1. 目录改名：`cookie_acquisition/` → `cookies/`
2. 迁移 `CookieManager`：从 `parser.py` 移到 `cookies/manager.py`
3. 统一所有引用

---

## Step 1：目录改名 + 迁移 CookieManager

```bash
# 1. 目录改名
git mv app/services/cookie_acquisition app/services/cookies

# 2. 新建 cookies/manager.py，把 CookieManager 类从 parser.py 移过来
#    保留 parser.py 里的 get_cookie_manager() 作为兼容 import 入口
```

**`cookies/manager.py` 包含：**
- `CookieManager` 完整类（从 `parser.py` 剪切）
- `get_cookie_manager()` 单例函数

**`parser.py` 改为：**
```python
# 兼容层，避免改所有 import
from app.services.cookies.manager import CookieManager, get_cookie_manager
```

---

## Step 2：更新 `cookies/` 内部 import

`cookies/` 目录内的文件引用了彼此：

| 文件 | 需要更新的 import |
|------|-------------------|
| `cookies/platforms/bilibili.py` | `from ...manager import ...` |
| `cookies/platforms/douyin.py` | 同上 |
| `cookies/patchright_manager.py` | 引用 CookieManager 的地方 |
| `cookies/qrcode_manager.py` | 同上 |

---

## Step 3：更新外部引用

搜索全项目所有引用 `cookie_acquisition` 的地方：

```bash
grep -rn "cookie_acquisition" app/ --include="*.py"
```

典型引用位置：
- `parser.py`（已处理，兼容层）
- `download.py` / `services/download/platforms/*.py`
- 前端 API 调用（如果有路径引用）

---

## Step 4：确认 CookieManager 公共方法完整

确保 `cookies/manager.py` 的 `CookieManager` 包含以下公共方法：

| 方法 | 用途 |
|------|------|
| `get_cookie_file(platform)` | **（新增）** 返回 Cookie 文件路径，不存在则从 DB 重建 |
| `save_cookie(platform, content)` | 保存 Cookie 到 DB + 磁盘 |
| `delete_cookie(platform)` | 删除 Cookie |
| `list_cookies()` | 列出所有平台 Cookie 状态 |
| `get_cookiejar_for_url(url)` | 返回内存 CookieJar（给 httpx 用）|
| `_get_cookie_file_path(platform)` | 内部方法，返回磁盘路径 |

---

## Step 5：验证

```bash
# 1. 语法检查
python -m py_compile app/services/cookies/*.py
python -m py_compile app/services/parser.py

# 2. 启动服务器，测试：
#    - B站解析（走 parser.py → CookieManager）
#    - B站下载（走 services/download/platforms/bilibili.py → CookieManager.get_cookie_file()）
#    - Twitter 下载（走 services/download/platforms/twitter.py → CookieManager.get_cookie_file()）
```

---

## 风险

| 风险 | 缓解 |
|------|------|
| import 路径改漏了 | Step 3 全项目搜索 `cookie_acquisition`，逐一改 |
| `parser.py` 兼容层失效 | 保留 `from ... import` 兼容至少 1 个版本，下个大版本再清 |
| Cookie 文件重建逻辑有 bug | 先在 `get_cookie_file()` 里加 try/except，失败返回 None 不崩 |

---

## 不改的东西（本次不碰）

- `services/download/` 新架构：能用就先留着，后续单独评估是否回滚
- 前端 API 路径：不改，Cookie 管理是纯后端重构
- 数据库 schema：`PlatformConnection` 表不动
