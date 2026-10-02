"""Telegram 平台元数据。

⚠️ **免登录**（公开频道用 `t.me/s` 预览页取），所以 `no_login=True`。

## ⚠️ 评评论**无解**（所以 capabilities 里没有 `comments`）

`t.me/s` 预览页**不含评论**。取评论要走 MTProto，
且公开频道的评论通常在**关联群组**里 —— 语义与其它平台不同
（不是"这条消息的回复"，而是"群的讨论"）。

## 探针关键词要用 "telegram"

⚠️ Telegram 的"频道消息"tab 填的是**频道名**而不是普通关键词 ——
实测探测时如果用"美食"会搜不到任何频道。
"""
PLATFORM_META = {
    "name": "telegram",
    "aliases": [],
    "conn_platform": "TELEGRAM",
    "cookie_domain": "t.me",
    "no_login": True,
    "probe_search_type": "channel",
    # ⚠️ 用频道名（不是普通关键词）—— 见上方说明
    "probe_keyword": "telegram",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        # ⚠️ 没有 "comments" / "self_profile" —— 见上方说明
    ],
}
