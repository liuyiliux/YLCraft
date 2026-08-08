"""
YLCraft — 番茄小说作家后台 API 端点定义

所有接口均为「作家后台 Web API」，域名为 fanqienovel.com。
已验证（2026-08-01，cookie 实测返回 code:0）：
  - POST /api/author/article/cover_article/v0/   存草稿（章节正文）
  - GET  /api/author/short_article/douyin_hot_list/v0/  热门故事（灵感）

未抓包、待 Phase 3 补齐（已验证可访问但字段未完全解析）：
  - GET /api/author/stats/book_list/v0/           我的书籍列表
  - GET /api/author/stats/book_common_v1/v0/      单本书统计
"""
from __future__ import annotations

# 番茄作家后台基础域名
BASE_URL = "https://fanqienovel.com"

# =============================================================================
# 已验证接口
# =============================================================================

# 存草稿 / 发布章节正文（POST, form-urlencoded）
COVER_ARTICLE = "/api/author/article/cover_article/v0/"

# 热门故事 / 开书灵感（GET）
DOUYIN_HOT_LIST = "/api/author/short_article/douyin_hot_list/v0/"

# =============================================================================
# 已验证可访问、待 Phase 3 解析字段
# =============================================================================

# 我的书籍列表（GET）
BOOK_LIST = "/api/author/stats/book_list/v0/"

# 单本书统计（阅读/追读/投票等）（GET）
BOOK_COMMON = "/api/author/stats/book_common_v1/v0/"

# =============================================================================
# 应用标识（稳定常量，非签名）
# =============================================================================

DEFAULT_AID = "2503"
DEFAULT_APP_NAME = "muye_novel"

# =============================================================================
# 签名参数「抓包得到的静态默认值」
# -----------------------------------------------------------------------------
# 说明：番茄作家后台的 Web 接口带 msToken / a_bogus / x-secsdk-csrf-token 等
# 反爬签名参数。实测表明，使用下面这组「抓包得到的静态值」即可返回 code:0，
# 服务端对上述签名的校验较为宽松（至少 cover_article / douyin_hot_list 如此）。
# 因此 Phase 0 直接以它们为默认值即可跑通；若后续服务端收紧校验导致失败，
# 需在 Phase 2/3 通过浏览器实时抓取并刷新以下常量，或改为从响应/页面动态提取。
# a_bogus 在抓包时是 URL 编码的，这里存「解码后」的原始值，交由 httpx 统一编码。
# =============================================================================

# --- cover_article/v0 用 ---
COVER_MS_TOKEN = (
    "opLRNB9UAhggymGE8LlABDCtNgwaXPWNEk6wgcfBmHFn2VNMz_xqmQewlJFBr3GfeaRKfW1s"
    "PDvAnfaJnO62lXqZgJD83fcUQMAieUQ8X40FcuacxDL1ELvttcbKXDHrVDeHKTOdgdjwoup"
    "FN2g3zq3ciHUj4GYcIBDpcLxBXqDX"
)
COVER_A_BOGUS = (
    "Ev0RhHWLOdR5CpAbuKDA9-oliwVMrTuywBTdR7DCeOKjP1lcqQpbKrt2coOjjnR-XbpWkKlH"
    "/rPcSjxbYb5ylFFkFmhDupTRHTIVnX0Lg1qVaUk8LHRQCusoeJab8cTimQoyJIUUAtQP2nQ4"
    "Dra0Ud59CApjsO7pKHrbdBUaT9tfgMs9BHqduNbDOXFcRbIRbD=="
)
X_SECSDK_CSRF_TOKEN = (
    "000100000001547a999222e4ed7eeac24bef70766c3502eba28ec3c74f12495512a115219"
    "54918c7abe0189f2f6f"
)

# --- douyin_hot_list/v0 用 ---
HOT_MS_TOKEN = (
    "J0Gfo_nx2a6_n_aegZ2hCueFcC2hNkV6B5Tb0TirRy-8OOdSDCY726yPLRV92SIXmWqkeTRqu"
    "3ps8IrC8JJWvI6o7YfFj_z-i_5-nRfErhGSmX19_ZmvHjOFO9Be97jhRpOgwvte-ni6JuxXaV"
    "2K7V0lgJTZxT4zAEWsZ1R8qSmA"
)
HOT_A_BOGUS = (
    "D60fgtSyQdRbe3AS8cPjHfpUi1D/NTWy-MT2bujC7PzpPH0c05pWKcSobxLOdLfGvupSkqqHki"
    "-lenncub4i1qHpzmpvui0SrtAnnW6L2qikb0t0EHfOCumwHJGPWmwqz/KRJARU10OaIV54Drr"
    "TUBl9eApEsYXpKrrfdQUaO9eD6MT9MNqKuPGdOhMc0C57"
)
