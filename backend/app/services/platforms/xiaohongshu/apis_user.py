"""YLCraft — 小红书 Web API 端点定义。

## 来源说明

本文件的端点**全部经实测验证**（2026-09-27），
并与开源项目交叉核对（详见 `docs/research/user_api_cross_validation.md`）。

## ⚠️ 小红书与抖音最大的区别：必须签名

小红书**所有** API 都要求 `X-s` / `X-s-common` / `xsc` 签名，
缺签名返回 `{"code": -1, "msg": "create invalid signature"}`。
（我方实测：抖音当前不需要签名，小红书必须。见 `signing.py`。）

## 为什么之前把"用户搜索"误判为做不了（值得记录）

我一开始用 Playwright 监听响应，按「响应体含 `nickname` + `follower_count`」
过滤 —— **没命中**，于是错误地推断"没有这个接口"。实际：
  · `search/usersearch` 的字段是 `name` / `fans`（字符串 "140.9万"）
  · `user/otherinfo` 的资料在 `data.basic_info`，也没有 `follower_count`

✅ **教训：按 URL 路径过滤，不要按响应体字段猜。**
"""

# =============================================================================
# 主机
# =============================================================================

# 主 API 主机（签名域名）。实测：user_posted / user/otherinfo / search/usersearch
# 都在这台机器上。
API_HOST = "https://edith.xiaohongshu.com"

# 搜索 API 主机（笔记搜索在这个域；用户搜索在 edith）
SEARCH_HOST = "https://so.xiaohongshu.com"

# 网页主机（页面访问用）
WEB_HOST = "https://www.xiaohongshu.com"

# =============================================================================
# 用户相关端点（2026-09-27 实测打通）
# =============================================================================

# 用户搜索（POST，**不是 GET**）
#
#   POST /api/sns/web/v1/search/usersearch
#   body: {"search_user_request": {
#              "keyword": "美食", "search_id": <必需,见 signing.get_search_id()>,
#              "page": 1, "page_size": 20,
#              "biz_type": "web_search_user",
#              "request_id": "<秒级>-<毫秒级>"}}
#   → {"code":1000,"success":true,"data":{"users":[{id,name,image,fans,
#                                                  sub_title,xsec_token,...}],
#                                          "has_more":bool,"result":{...}}}
#
# 实测「美食」→ 20 个用户（吕小厨爱美食 140.9万粉…）
#
# ⚠️ 区分搜用户/搜笔记靠 **URI 路径**（usersearch vs notes）和 body 里的
#    `biz_type`，**不是**页面上的 `type=54` 参数——那只是前端路由参数。
USER_SEARCH = "/api/sns/web/v1/search/usersearch"

# 用户资料（GET）——查**他人**
#
#   GET /api/sns/web/v1/user/otherinfo?target_user_id={user_id}
#   → {"code":0,"data":{"basic_info":{nickname, red_id, desc, images,
#                                     imageb, gender, ip_location},
#                       "interactions":[{count,type},...],
#                       "tags":[...], "extra_info":{...}, ...}}
#
# 实测（逸流AI）：昵称=逸流AI  red_id=95645311698
#                 简介='分享ai知识，入口，提示词'
#
# 注意：**粉丝数不在 basic_info 里**——在 `interactions` 数组里
#       （每项 {count, type}，type 如 "fans"/"follows"/"interaction"）。
USER_OTHERINFO = "/api/sns/web/v1/user/otherinfo"

# 查自己（GET，无需参数）。
#
#   GET /api/sns/web/v2/user/me
#   → {"code":0,"data":{user_id, nickname, desc, gender, imageb,
#                       red_id, guest, xsec_token, images}}
#
# ⚠️ **不含粉丝数/关注数/作品数** —— 拿到 user_id 后要再调
#    `USER_OTHERINFO` 补统计（见 user.get_self_profile）。
#
# 实测（账号本人）：昵称=逸流AI  red_id=95645311698
#                   desc=分享ai知识，入口，提示词
USER_SELFINFO = "/api/sns/web/v2/user/me"

# 旧版自查端点（保留常量以便对照，未使用）
USER_SELFINFO_V1 = "/api/sns/web/v1/user/selfinfo"

# 用户作品列表（GET）
#
#   GET /api/sns/web/v1/user_posted
#       ?num=20&cursor=&user_id={user_id}&image_scenes=FD_WM_WEBP
#   → {"code":0,"data":{"notes":[{note_id,type,display_title,...}],
#                       "has_more":true,"cursor":"69b187880000000015033a97"}}
#
# 分页：首页 `cursor` 传**空串**，之后用响应里的 `cursor`。
# 实测（逸流AI）：20 条 / has_more=True
USER_POSTED = "/api/sns/web/v1/user_posted"

# 备选用户搜索（**前缀是 `web_api` 不是 `api`**）
#
# 这是创作者中心"发笔记 @ 人"的联想搜索接口，返回 `user_info_dtos`。
# 作为 USER_SEARCH 的备选（来源：ReaJason/xhs）。
USER_SEARCH_ALT = "/web_api/sns/v1/search/user_info"

# 笔记搜索（已有实现走的端点，仅作对照记录）
NOTE_SEARCH = "/api/sns/web/v2/search/notes"
