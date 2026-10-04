"""微博平台元数据。

## ⚠️ 两个实测坑（都写在这里，避免各处重复踩）

1. **cookie_domain 必须是 `"weibo"`**，不是 `"weibo.com"` ——
   实测主站 weibo.com 的 cookie 在 `m.weibo.cn` **无效**
   （`api/config` 返回 `login:false`）。

2. **楼中楼（`replies`）能取到** —— 2026-10-04 实测推翻原来的"拿不到"。

   原来的结论是"顶层评论的 `comments` 字段实测 20 条里 0 条带"，
   并拿 MediaCrawler（★66k）"也只读 comments、默认开关关着"做交叉验证。
   **两处都不成立**：
     · 那批"0 条"是**抽样**抽到的另一批内容。换成确定有楼中楼的样本
       （5336295257679240），顶层 20 条**全部**带 `comments`（共 32 条），
       `rootid` 零串号。
     · 「别人也没实现」**不能**证明「平台没有这个数据」。

   这是同一个坑的第三次：快手（`reply_count=0` → 写"取不到"）、
   B站（信了文档说"随顶层返回"，实际数组全空）、微博（抽样没抽到）。

   ⚠️ 另：微博顶层评论的 `reply_count` 字段**恒为 0**（实测 20/20），
   所以 `client.py` 里是自己数 `len(comments)` —— 否则前端那个
   `reply_count > 0` 的判断会让用户**永远看不到回复入口**。
"""
PLATFORM_META = {
    "name": "weibo",
    "aliases": ["wb"],
    "conn_platform": "WEIBO",
    # ⚠️ 是 "weibo" 不是 "weibo.com"（见上方说明）
    "cookie_domain": "weibo",
    "no_login": False,
    "probe_search_type": "note",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        "self_profile",      # 「我的数据」
        "comments",          # /comments/hotflow（纯 HTTP）
        # ✅ 楼中楼能取（2026-10-04 实测：顶层 20/20 都带 comments，
        #    共 32 条，rootid 零串号）—— 此前"拿不到"是抽样造成的误判
        "replies",
    ],
}
