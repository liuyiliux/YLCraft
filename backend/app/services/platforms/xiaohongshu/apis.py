"""
YLCraft — 小红书 API 端点定义

⚠️ 2026-09-26 抓包实测更正（browser-skill 接管用户已登录 Chrome）：
   搜索端点**已迁移**，下面 SEARCH_NOTES 里那个旧的 edith/v1 地址**已失效**——
   实测返回 {"code":300011,"msg":"当前账号存在异常，请切换账号后重试"}
   （本质是缺 X-s/X-t 签名被风控拒绝，不是账号真的异常）。

   真实端点是：
       POST https://so.xiaohongshu.com/api/sns/web/v2/search/notes
   域名从 edith 变成 so，版本从 v1 变成 v2。

   为什么没有直接把常量改成新地址就完事：该接口要 X-s/X-t 签名，
   签名函数 window._webmsxyw 是混淆 JS，且在 www 页面上跨域调 so 域会被
   拒（实测 406）。所以小红书搜索改走 Patchright（见 search_patchright.py），
   SEARCH_NOTES 保留旧值仅作历史记录，新代码不要用它。
"""

# 基础 URL
BASE_URL = "https://www.xiaohongshu.com"

# 搜索 API
#
# ⚠️ 已失效，勿用于新代码（见模块 docstring）。真实端点：
#    https://so.xiaohongshu.com/api/sns/web/v2/search/notes
SEARCH_NOTES = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"

# 搜索页（Patchright 用它打开页面自己搜，绕开签名）
SEARCH_PAGE = "https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_explore_feed"

# 笔记详情 API
NOTE_DETAIL = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"

# 用户主页 API
USER_PROFILE = "https://www.xiaohongshu.com/api/sns/web/v1/user/otherinfo"

# 用户笔记列表 API
USER_NOTES = "https://www.xiaohongshu.com/api/sns/web/v1/user_posted"

# 评论 API
COMMENTS = "https://www.xiaohongshu.com/api/sns/web/v2/comment/page"

# 请求头模板
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.xiaohongshu.com/",
    "Origin": "https://www.xiaohongshu.com",
    "X-Requested-With": "XMLHttpRequest",
}
