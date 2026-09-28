"""YLCraft — 微博 Web API 端点定义。

## 来源与验证

搜索端点来源：MediaCrawler `media_platform/weibo/client.py::get_note_by_keyword`；
搜索类型枚举来源：MediaCrawler `media_platform/weibo/field.py::SearchType`；
**响应结构由我方在真实浏览器内实测确认**（2026-09-27）。

## ⚠️ 与抖音/小红书最大的区别：必须登录

实测（不带 Cookie 直接请求）：

    GET https://m.weibo.cn/api/container/getIndex?...   → HTTP 432（len=0）
    访问 m.weibo.cn / weibo.com / s.weibo.com
        → 全部重定向到 Sina Visitor System
    带访客 Cookie 调搜索 → {"ok":-100,
        "url":"https://passport.weibo.com/sso/signin?entry=wapsso..."}

**在用户已登录的浏览器里，同一 URL 返回 `ok=1`、total=739~854 条。**

所以微博必须有真实登录 Cookie：
  · 抖音：当前不需要签名/登录（实测）
  · 小红书：需要**签名**（xhshow），登录态也要
  · 微博：需要**登录态**（无签名机制）

## 判定登录态的关键

搜索响应里 `ok` 字段：
  · `ok == 1`  → 正常，`data.cards` 有内容
  · `ok == -100` → **未登录**，响应体里带 `url` 指向登录页

⚠️ 不要把 `ok == -100` 当成"没搜到结果"——
那是登录态问题，报"关键词无结果"会把人带偏。
"""

# 移动端 API 主机（搜索/详情都在这）
MOBILE_HOST = "https://m.weibo.cn"

# 搜索（GET）—— 2026-09-27 在真实浏览器内实测确认
#
#   GET /api/container/getIndex
#       ?containerid=100103type={type}&q={关键词}
#       &page_type=searchall
#       &page={页码}
#
#   实测返回：
#   {"ok":1,"data":{"cards":[{"card_type":9,"mblog":{...}}, ...],
#                    "cardlistInfo":{"total":739, ...}}}
#
#   cards 里混着 card_type=9（微博正文，有 mblog）与 11（广告/运营，跳过）
SEARCH = "/api/container/getIndex"

# 搜索容器 ID 前缀（`100103` + `type=` + 类型 + `&q=` + 关键词）
SEARCH_CONTAINER_PREFIX = "100103"

# 搜索页类型（固定值，实测）
SEARCH_PAGE_TYPE = "searchall"

# 微博卡片类型：只有 9 带 mblog（正文）
CARD_TYPE_MBLOG = 9

# 用户卡片（card_type=11 → card_group[] 里每项有 `user` 对象）
#
# ⚠️ 与内容搜索**结构完全不同**：
#     内容：cards[].card_type=9  → .mblog
#     用户：cards[].card_type=11 → .card_group[].user
CARD_TYPE_USER_GROUP = 11

# 用户主页容器前缀（`100505` + uid）
#
# 实测（2026-09-28）：
#     GET /api/container/getIndex?containerid=100505{uid}
#     → data.userInfo{...}      ← 直接是用户对象（29 个字段）
# 与 MediaCrawler `get_creator_info_by_id` 的做法一致。
USER_CONTAINER_PREFIX = "100505"

# 用户搜索的 type（**实测确认**）
#
#     GET /api/container/getIndex
#         ?containerid=100103type=3&q={关键词}&page_type=searchall&page=N
#     → cards[].card_type=11 → card_group[] → user{}
#     实测一页 20 个用户
SEARCH_TYPE_USER = "3"


# =============================================================================
# 搜索类型（来源 MediaCrawler field.py::SearchType）
# =============================================================================

SEARCH_TYPE_DEFAULT = "1"     # 综合
SEARCH_TYPE_REALTIME = "61"   # 实时
SEARCH_TYPE_POPULAR = "60"    # 热门
SEARCH_TYPE_VIDEO = "64"      # 视频

# 前端 search_type → 微博 type
SEARCH_TYPE_ALIASES: dict[str, str] = {
    "note": SEARCH_TYPE_DEFAULT,      # 前端「笔记/图文」统称
    "all": SEARCH_TYPE_DEFAULT,
    "default": SEARCH_TYPE_DEFAULT,
    "realtime": SEARCH_TYPE_REALTIME,
    "popular": SEARCH_TYPE_POPULAR,
    "video": SEARCH_TYPE_VIDEO,
    # 兼容前端可能传的英文别名
    "hot": SEARCH_TYPE_POPULAR,
}


def resolve_search_type(search_type: str | None) -> str:
    """把前端的 search_type 解析成微博的 type 值。

    未知值回退到综合（不抛错——用户选了没实现的类型时，
    给「综合」结果比给报错更有用）。
    """
    key = (search_type or "").strip().lower()
    return SEARCH_TYPE_ALIASES.get(key, SEARCH_TYPE_DEFAULT)


def build_search_params(
    keyword: str,
    page: int = 1,
    search_type: str | None = None,
) -> dict[str, str]:
    """构造搜索查询参数。

    `containerid` 的格式是 `100103type={type}&q={关键词}` ——
    注意关键词**直接拼在 containerid 里**，不是独立的 q 参数
    （实测确认，这点很容易写错）。
    """
    stype = resolve_search_type(search_type)
    return {
        "containerid": f"{SEARCH_CONTAINER_PREFIX}type={stype}&q={keyword}",
        "page_type": SEARCH_PAGE_TYPE,
        "page": str(page),
    }


def build_user_search_params(keyword: str, page: int = 1) -> dict[str, str]:
    """构造**用户搜索**参数（实测确认）。

        GET /api/container/getIndex
            ?containerid=100103type=3&q={关键词}&page_type=searchall&page=N
        → cards[].card_type=11 → card_group[] → user{}
        实测一页 20 个用户

    ⚠️ 与内容搜索的唯一区别是 `type=3`（内容综合是 `type=1`）。
        用户卡片走 `card_type=11` + `card_group`，
        内容卡片走 `card_type=9` + `mblog` —— **解析方式完全不同**。
    """
    return {
        "containerid": f"{SEARCH_CONTAINER_PREFIX}type={SEARCH_TYPE_USER}&q={keyword}",
        "page_type": SEARCH_PAGE_TYPE,
        "page": str(page),
    }


def build_user_detail_params(uid: str) -> dict[str, str]:
    """构造用户详情参数（实测确认）。

        GET /api/container/getIndex?containerid=100505{uid}
        → data.userInfo{...}

    与 MediaCrawler `get_creator_info_by_id` 一致（它还额外带
    jumpfrom/type/value，实测只带 containerid 也能用）。
    """
    return {"containerid": f"{USER_CONTAINER_PREFIX}{uid}"}
