"""
YLCraft — 小红书 API 端点定义
"""

# 基础 URL
BASE_URL = "https://www.xiaohongshu.com"

# 搜索 API
SEARCH_NOTES = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"

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
