"""快手平台元数据。

## ⚠️ 两个反直觉的实测结论

1. **搜索签名必须从浏览器抓**（`__NS_hxfalcon` 是混淆 JS，纯 HTTP 拿不到），
   但**评论不需要签名**！决定性对照（同一 cookie、同一时刻）：

       /rest/v/search/feed        无签名 → {"result":50,"签名验证失败"}
       /rest/v/photo/comment/list 无签名 → {"result":1,...} ✅

2. **没有 `get_user_profile`** —— 这不是漏做，是**平台没有这个接口**
   （用搜索反查 userId 也不行：搜索按昵称/内容索引，不按 uid）。
   所以 capabilities 里**没有** `user_profile`。
"""
PLATFORM_META = {
    "name": "kuaishou",
    "aliases": ["ks"],
    "conn_platform": "KUAISHOU",
    "cookie_domain": "kuaishou",
    "no_login": False,
    "probe_search_type": "note",
    "capabilities": [
        "search", "detail", "search_users",
        # ⚠️ 没有 "user_profile" —— 平台无此接口（见上方说明）
        "user_videos",
        "self_profile",      # 「我的数据」（/rest/v/profile/get）
        "comments",          # 免签名
        "replies",           # /rest/v/photo/comment/sublist（也免签名）
    ],
    # ⚠️ 快手登录态**约 20 分钟**就失效（服务端控制，无法延长），
    #    所以博主中心的"点用户看资料"退化用搜索结果里的数据。
    "user_dimension": True,
}
