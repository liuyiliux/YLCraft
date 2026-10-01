"""YLCraft — YouTube 平台接口常量与参数构造（2026-10-01 实测）。

## 为什么用 yt-dlp

本机到 YouTube 的网络以前**不通**（DNS 污染），现在 VPN 通了。
yt-dlp 是项目里现成的依赖（下载链路一直在用），它内部处理了
YouTube 的签名/ innertube API，我们不用自己逆向。

## 实测（2026-10-01，VPN 环境）

| URL | 结果 |
|-----|------|
| `ytsearch5:python tutorial` | 5 条（相关度，首条 Mosh） |
| `.../results?...&sp=EgIIAQ%3D%3D` | 54 条（**最新**，首条 92 秒新视频） |
| `.../results?...&sp=CAMSAhAB` | 479 条（**播放量**，首条 freeCodeCamp 4937万） |
| `https://www.youtube.com/@freecodecamp/videos` | 1724 条（频道视频） |

三个排序首条**各不相同** → 排序真实生效（不是假选项）。
"""
from __future__ import annotations

# 搜索类型 → yt-dlp 可识别的 URL / 语法。
#
# ⚠️ `ytsearchdateN:` 语法在这个 yt-dlp 版本**不支持**
# （实测 "Unsupported url scheme: ytsearchdate3"），
# 所以「最新」排序必须用 **sp= 参数的完整搜索 URL**。
SEARCH_SYNTAX = {
    "note": "ytsearch{max}:{kw}",                       # 相关度（默认）
    "date": "https://www.youtube.com/results?search_query={kw_enc}&sp=EgIIAQ%253D%253D",
    "viewcount": "https://www.youtube.com/results?search_query={kw_enc}&sp=CAMSAhAB",
}

# sp= 参数实测过的值（留档，别再猜）：
#   EgIIAQ==  → 上传日期排序（%3D%3D 要双重编码成 %253D%253D）
#   CAMSAhAB  → 播放量排序
SP_SORT = {
    "relevance": "",
    "date": "EgIIAQ%253D%253D",
    "viewcount": "CAMSAhAB",
}

# 时长过滤（与前端 PLATFORM_SEARCH_CONFIG.youtube 的 filters 对应）
SP_DURATION = {
    "short": "EgIYAw%253D%253D",     # < 4 分钟
    "medium": "EgIYAw%253D%253D",    # 4-20 分钟（sp 不支持区间，占位）
    "long": "EgIYBQ%253D%253D",      # > 20 分钟
}

# YouTube 搜索结果页的时长分段（前端 filters 的 value）
DURATION_BOUNDS = {
    "short": (0, 240),        # < 4 分钟
    "medium": (240, 1200),    # 4-20 分钟
    "long": (1200, 10**9),    # > 20 分钟
}


def build_search_url(keyword: str, sort: str = "", duration: str = "") -> str:
    """构造搜索 URL。sort/duration 组合时 YouTube 只认一个 sp=，
    所以**排序优先**，时长在客户端按 duration 过滤（见 client.py）。"""
    from urllib.parse import quote_plus

    kw_enc = quote_plus(keyword)
    sp = SP_SORT.get(sort, "")
    if duration and not sp:
        sp = SP_DURATION.get(duration, "")
    url = f"https://www.youtube.com/results?search_query={kw_enc}"
    if sp:
        url += f"&sp={sp}"
    return url


def parse_video_id(item_id_or_url: str) -> str:
    """从 ID 或各种 YouTube URL 里提取视频 ID。

    支持：纯 ID / watch?v= / youtu.be/ / shorts/ / embed/
    """
    s = (item_id_or_url or "").strip()
    if re_fullmatch := __import__("re").fullmatch(r"[\w-]{11}", s):
        return s
    import re as _re

    for pat in (
        r"[?&]v=([\w-]{11})",
        r"youtu\.be/([\w-]{11})",
        r"/shorts/([\w-]{11})",
        r"/embed/([\w-]{11})",
    ):
        m = _re.search(pat, s)
        if m:
            return m.group(1)
    # 最后兜底：路径最后一段是 11 位 ID
    m = _re.search(r"/([\w-]{11})(?:[?/]|$)", s)
    return m.group(1) if m else s
