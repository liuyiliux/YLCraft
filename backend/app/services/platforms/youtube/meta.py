"""YouTube 平台元数据。

⚠️ **免登录** —— 公开频道数据用 yt-dlp 直接取，不需要 Cookie。
所以 `no_login=True`，接口层不会去找连接。

## 评论（2026-10-01 加）

走 yt-dlp 的 innertube 实现，**必须设 `max_comments` 上限** ——
不设就是无上限翻页（实测某视频报 ~1063 万条评论，跑了 10 分钟没停）。

没有"子回复"能力：yt-dlp 返回的是**平铺列表**，回复靠 `parent` 字段标识，
我们目前只取顶层（`parent == "root"`）。

## ⚠️ 详情 + 评论：会被 YouTube 人机校验**按视频**拦截（2026-10-04 实测）

症状：`Sign in to confirm you're not a bot` → 接口 500。

**先纠正一个容易犯的误判**：这句话**不是**"必须登录才能看评论"。
实测同一 IP、同一分钟、默认 client、无 cookie：

    搜索    4/4 全通（16 / 299 / 257 / 7 条）
    watch   dQw4w9WgXcQ ✅ 240 万条评论
            njK0eebUsQw / 9bZkp7q19f0 ❌ not a bot

→ 不是全局 IP 封禁，是**按视频**加严。扩到 8 个视频（含 Despacito /
Adele Hello / Happy）成功 **1/8**。

已逐个试过、**全部无效**的手段（别再试了）：

    player_client = web / web_safari / web_embedded / android / ios /
                    tv / mweb                      7 个全试，失败视频一律失败
    player_skip   = webpage                        跳过 HTML 直连 innertube，仍失败
                    js,webpage,html                仍失败
    cookiesfrombrowser = edge                      cookie 读得到，仍失败

⚠️ `web_embedded` / `mweb` **有副作用**：会把本来能用的 dQw4w9WgXcQ 也弄坏
（`Requested format is not available`），所以**不能**当后备方案。

⚠️ **详情页和评论页是同一个失败**（都走 `extract_info(watch)`）——
所以搜出结果点进去一样 500，不只是评论的问题。

处置：按 `RiskControlError` 抛（→ 上层 **429**，提示等一等 / 换 IP），
不是裸 RuntimeError（→ 500）。500 语义是"我们坏了"，会误导排查方向。

所以 `comments` 能力**部分可用**（实测能拿到评论），但**不稳定**，
不保证每个视频都取得到 —— 前端/文档不要写成"必然失败"或"必然成功"。
"""
PLATFORM_META = {
    "name": "youtube",
    "aliases": [],
    "conn_platform": "YOUTUBE",
    "cookie_domain": "youtube",
    # ⚠️ 免登录（yt-dlp 直接取公开数据）
    "no_login": True,
    "probe_search_type": "video",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        # ⚠️ comments + detail 都可能被 YouTube 人机校验按视频拦（见上方）
        #    —— 能拿到，但不是每个视频都拿得到。**不要**因此删掉这行：
        #    实测 dQw4w9WgXcQ 就能正常返回评论。
        "comments",
        # ⚠️ 没有 "replies" / "self_profile" —— 见上方说明
    ],
    # 免登录平台没有"我的账号"概念 → 不进「我的数据」页
    "user_dimension": True,
}
