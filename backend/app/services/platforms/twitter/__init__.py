"""YLCraft — 推特/X 平台模块。

## 实测结论（2026-09-28）

**搜索强制要求登录。** 用 Patchright 全新 profile（真·未登录）打开：

    https://x.com/search?q=美食&src=typed_query
    → 重定向到 https://x.com/i/jf/onboarding/web?redirect_after_login=%2Fsearch...
    → article 数 = 0

**注意别被 `document.cookie` 误导**：`auth_token` 是 httpOnly，看不到 ≠ 没登录。
可靠判据是**只有登录后才出现的界面元素**（发帖 / 账号菜单）。

与微博对比：
  · 微博：**实测免登录可搜**（`ok=1, total=870`）
  · 推特：**必须登录**

所以推特要能用，前提是用户在 YLCraft 的浏览器 profile 里登录过一次推特。
未登录时会抛 `TwitterLoginRequiredError`（可操作提示），
而不是返回"0 条结果"。
"""
from .client import TwitterClient
from .search_dom import (
    TwitterLoginRequiredError,
    parse_aria_counts,
    parse_tweet,
    upgrade_image_url,
)

__all__ = [
    "TwitterClient",
    "TwitterLoginRequiredError",
    "parse_tweet",
    "parse_aria_counts",
    "upgrade_image_url",
]
