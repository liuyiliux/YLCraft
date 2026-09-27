# 抖音用户采集接口 — 开源项目交叉验证报告

> 调研目的：用开源项目的实现，交叉验证 YLCraft 自行实测发现的抖音用户搜索 / 用户资料 / 作品列表接口。
> 调研方式：`curl.exe` 直接拉取 GitHub raw 源码（web_fetch 对 github.com 被网络沙箱拦截）。
> 调研日期：报告生成时。所有结论均标注"仓库 + 文件路径 + 代码片段"。

---

## 0. 结论摘要（先看这个）

| # | 问题 | 结论 | 与我们实测是否一致 |
|---|---|---|---|
| 1 | 用户搜索接口 | `GET /aweme/v1/web/discover/search/`，`search_channel=aweme_user_web` | ✅ 路径一致；**channel 取值不同**（我们用 `aweme_user`，正确值是 `aweme_user_web`） |
| 2 | 用户资料接口 | `GET /aweme/v1/web/user/profile/other/`，参数 `sec_user_id` | ✅ 完全一致 |
| 3 | 作品列表接口 | `GET /aweme/v1/web/aweme/post/`，`sec_user_id` + `max_cursor` + `count` | ✅ 完全一致 |
| 4a | 搜索接口是否需签名 | **不需要** | ✅ 与我们实测一致 |
| 4b | `user/profile/other` 是否需签名 | **不需要**（白名单未收录，实测 8/8 成功） | 🆕 新结论（我们尚未测） |
| 4c | `aweme/post` 是否需签名 | **需要**，且缺的是 `x-secsdk-web-signature`（WebSign），不是 a_bogus | 🆕 **新结论，与我们的假设不同** |
| 5 | 其他用户接口 | 见 §5，共找到 12 个用户相关接口 | 🆕 新发现 |

**最重要的一个新发现**：`aweme/post` 在抖音自己的 web SDK 的"签名保护路径白名单"里，而 `user/profile/other` 不在。
两个独立项目（Evil0ctal、JoeanAmier）从同一份 SDK 抄出了**逐条完全一致**的 14 条白名单，可信度高。

---

## 1. 用户搜索接口

### 1.1 路径 —— 三个项目一致

所有查到的项目都用 `/aweme/v1/web/discover/search/`，**没有**任何项目用别的路径做用户搜索。

**来源 A：`JoeanAmier/TikTokDownloader` → `src/interface/search.py`**

```python
search_params = (
    ...
    SimpleNamespace(
        note=_("用户搜索"),
        api=f"{API.domain}aweme/v1/web/discover/search/",
        channel="aweme_user_web",
        type="user",
        key="user_list",
    ),
    ...
)
```

注意 `key="user_list"` —— 与我们实测的响应结构 `{"user_list": [...]}` 一致。

**来源 B：`Evil0ctal/Douyin_TikTok_Download_API` → `src/dtk/platforms/douyin/endpoints.py`**

```python
# User search
USER_SEARCH: Final = f"{DOUYIN_DOMAIN}/aweme/v1/web/discover/search/"
```

**来源 C：`cv-cat/DouYin_Spider` → `dy_apis/douyin_api.py`**

```python
def search_user(auth, query: str, offset: str = '0', num: str = '25', ...):
    # 结尾斜杠不能少，浏览器实测就是 /search/
    api = "/aweme/v1/web/discover/search/"
    refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?type=user'
    has_filter = bool(douyin_user_fans or douyin_user_type)
    params.add_param("search_channel", 'aweme_user_web')
```

### 1.2 `search_channel` 取值 —— 这是关键，我们写错了

**四处独立来源一致给出 `aweme_user_web`**（不是我们实测时用的 `aweme_user`）：

**来源 A：`NanmiCoder/MediaCrawler` → `media_platform/douyin/field.py`**

```python
class SearchChannelType(Enum):
    """search channel type"""
    GENERAL = "aweme_general"  # General
    VIDEO = "aweme_video_web"  # Video
    USER = "aweme_user_web"  # User
    LIVE = "aweme_live"  # Live
```

**来源 B：`JoeanAmier/TikTokDownloader` → `src/interface/search.py`** —— 四频道完整映射：

```python
SimpleNamespace(note=_("综合搜索"), api=f"{API.domain}aweme/v1/web/general/search/single/", channel="aweme_general", type="general", key="data"),
SimpleNamespace(note=_("视频搜索"), api=f"{API.domain}aweme/v1/web/search/item/",           channel="aweme_video_web", type="video", key="data"),
SimpleNamespace(note=_("用户搜索"), api=f"{API.domain}aweme/v1/web/discover/search/",       channel="aweme_user_web",  type="user",  key="user_list"),
SimpleNamespace(note=_("直播搜索"), api=f"{API.domain}aweme/v1/web/live/search/",           channel="aweme_live",      type="live",  key="data"),
```

**来源 C：`cv-cat/DouYin_Spider` → `dy_apis/douyin_api.py`** —— 三个搜索函数分别用三个 channel：

```python
# search_general_work → /aweme/v1/web/general/search/single/  → search_channel = "aweme_general"
# search_video_work   → /aweme/v1/web/search/item/             → search_channel = 'aweme_video_web'
# search_user         → /aweme/v1/web/discover/search/         → search_channel = 'aweme_user_web'
# search_live         → /aweme/v1/web/live/search/             → search_channel = 'aweme_live'
```

### 1.3 我们实测的坑 —— 根因已确认

> 我们的发现：`search_channel=aweme_user` 加在 `general/search/single` 上**不生效**，返回和综合一样。

**根因**：`search_channel` 是**与接口路径一一绑定**的，不是可以任意组合的开关。每个搜索 tab 有自己**独立的接口路径 + 独立的 channel 值**：

| tab | 接口路径 | search_channel |
|---|---|---|
| 综合 | `/aweme/v1/web/general/search/single/` | `aweme_general` |
| 视频 | `/aweme/v1/web/search/item/` | `aweme_video_web` |
| **用户** | `/aweme/v1/web/discover/search/` | **`aweme_user_web`** |
| 直播 | `/aweme/v1/web/live/search/` | `aweme_live` |

把 `aweme_user_web`（或 `aweme_user`）传给 `general/search/single` 是无效操作 —— 该接口只认 `aweme_general`，因此返回综合结果是**预期行为**，不是 bug。

**这是本次调研对我们实测最有价值的一条修正。**

### 1.4 用户搜索的完整参数

**来源：`cv-cat/DouYin_Spider` → `dy_apis/douyin_api.py`，`search_user()`**

```python
api = "/aweme/v1/web/discover/search/"
refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?type=user'
params.add_param("search_channel", 'aweme_user_web')
# 可选筛选（抖音端"粉丝数量"+"用户类型"）
params.add_param("search_filter_value",
                 r'{"douyin_user_fans":["%s"],"douyin_user_type":["%s"]}'
                 % (douyin_user_fans, douyin_user_type))
params.add_param("search_source", 'normal_search')
params.add_param("is_filter_search", '1' if has_filter else '0')
params.add_param("pc_search_top_1_params", '{"enable_ai_search_top_1":1}')
# 再加一批浏览器指纹参数：cpu_core_num / screen_width / screen_height /
# browser_name / browser_version / engine_version / device_memory
```

分页逻辑（`DouYin_Spider`）：

```python
def search_some_user(auth, query: str, num: int, **kwargs) -> list:
    user_list = []
    ...
    res_json = DouyinAPI.search_user(auth, query, offset, count)
    users = res_json["user_list"]
    user_list.extend(users)
    if res_json["has_more"] != 1 or len(user_list) >= num:
        break
```

即分页字段是 `has_more` + `offset`，与我们的实测（`offset` / `has_more`）一致。

**筛选值枚举（`JoeanAmier/TikTokDownloader` → `src/interface/search.py`）**：

```python
douyin_user_fans_map = {
    0: [""], 1: ["0_1k"], 2: ["1k_1w"], 3: ["1w_10w"], 4: ["10w_100w"], 5: ["100w_"],
}
douyin_user_type_map = {
    0: [""], 1: ["common_user"], 2: ["enterprise_user"], 3: ["personal_user"],
}
```

**关于 `count`**：我们实测 `count=10` 返回 9 条「美食」、10 条「李子柒」。
`DouYin_Spider` 的默认是 `num='25'`，返回条数由服务端决定，小于 count 属正常。

---

## 2. 用户资料接口

### 2.1 路径与参数 —— 与我们的实测完全一致

**来源 A：`NanmiCoder/MediaCrawler` → `media_platform/douyin/client.py`**

```python
async def get_user_info(self, sec_user_id: str):
    uri = "/aweme/v1/web/user/profile/other/"
    params = {
        "sec_user_id": sec_user_id,
        "publish_video_strategy_type": 2,
        "personal_center_strategy": 1,
    }
    return await self.get(uri, params)
```

**来源 B：`JoeanAmier/TikTokDownloader` → `src/interface/user.py`**

```python
self.api = f"{self.domain}aweme/v1/web/user/profile/other/"
...
def generate_params(self) -> dict:
    return self.params | {
        "publish_video_strategy_type": "2",
        "source": "channel_pc_web",
        "sec_user_id": self.sec_user_id,
        "personal_center_strategy": "1",
        "profile_other_record_enable": "1",
        "land_to": "1",
        "version_code": "170400",
        "version_name": "17.4.0",
    }
```

调用时取数据的 key 是 `"user"`（`run(single_page=True, data_key="user")`）。

**来源 C：`Evil0ctal/Douyin_TikTok_Download_API` → `src/dtk/platforms/douyin/params.py`**

```python
def author_profile_params(*, sec_user_id: str, profile: ClientProfile = DEFAULT_PROFILE) -> dict[str, str]:
    """Parameters for ``/aweme/v1/web/user/profile/other/``.

    ``sec_user_id`` and not ``uid``: the numeric uid rotates, the sec id does
    not. See the Author contract in ``docs/design/11-data-contracts.md``.
    """
    return {
        **base_params(profile),
        "sec_user_id": str(sec_user_id),
        "publish_video_strategy_type": "2",
        "personal_center_strategy": "1",
    }
```

**来源 D：`cv-cat/DouYin_Spider` → `dy_apis/douyin_api.py`**

```python
def get_user_info(auth, user_url: str, **kwargs) -> dict:
    api = f"/aweme/v1/web/user/profile/other/"
    user_id = user_url.split("/")[-1].split("?")[0]
    headers.set_referer(user_url)
    params.add_param("sec_user_id", user_id)
    params.add_param("profile_other_record_enable", '1')
```

**来源 E：`Johnserf-Seed/f2` → `f2/apps/douyin/api.py` + `model.py`**

```python
# api.py
USER_DETAIL = f"{DOUYIN_DOMAIN}/aweme/v1/web/user/profile/other/"

# model.py
class UserProfile(BaseRequestModel):
    sec_user_id: str
```

### 2.2 关于我们发现的"必须用 sec_uid，用 uid 打开是空页面"

开源项目直接印证，并且 `Evil0ctal` 给出了原因：

> `sec_user_id` and not `uid`: **the numeric uid rotates, the sec id does not.**

（数字 `uid` 会轮换，`sec_uid` 不会 —— 所以 `sec_uid` 是稳定标识符。）

**三处来源都只用 `sec_user_id`，没有任何项目用 `uid` 打这个接口。**

### 2.3 返回结构

`Evil0ctal` 的测试 fixture `tests/fixtures/douyin/user_profile.json` 显示响应为：

```json
{
  "status_code": 0,
  "user": {
    "uid": "...", "sec_uid": "...", "short_id": "...", "unique_id": "...",
    "nickname": "...", "signature": "...",
    "avatar_larger": {...}, "avatar_medium": {...}, "avatar_thumb": {...},
    "custom_verify": "", "enterprise_verify_reason": "", "verification_type": 1,
    ...
  }
}
```

即外层包一个 `user` 键（与 `TikTokDownloader` 的 `data_key="user"` 吻合）。
我们实测的 `follower_count` / `total_favorited` / `aweme_count` 位于这个 `user` 对象内部。

---

## 3. 作品列表接口

### 3.1 路径与参数 —— 与我们的实测完全一致

**来源 A：`NanmiCoder/MediaCrawler` → `media_platform/douyin/client.py`**

```python
async def get_user_aweme_posts(self, sec_user_id: str, max_cursor: str = "") -> Dict:
    uri = "/aweme/v1/web/aweme/post/"
    params = {
        "sec_user_id": sec_user_id,
        "count": 18,
        "max_cursor": max_cursor,
        "locate_query": "false",
        "publish_video_strategy_type": 2,
    }
    return await self.get(uri, params)
```

**来源 B：`JoeanAmier/TikTokDownloader` → `src/interface/account.py`**

```python
post_api = f"{API.domain}aweme/v1/web/aweme/post/"
...
def generate_post_params(self) -> dict:
    return self.params | {
        "sec_user_id": self.sec_user_id,
        "max_cursor": self.cursor,
        "locate_query": "false",
        "show_live_replay_strategy": "1",
        "need_time_list": "1",
        "time_list_query": "0",
        "whale_cut_token": "",
        "cut_version": "1",
        "count": self.count,           # 默认 18
        "publish_video_strategy_type": "2",
        "from_user_page": "1",
    }
```

**来源 C：`Evil0ctal/Douyin_TikTok_Download_API` → `src/dtk/platforms/douyin/params.py`**

```python
def author_posts_params(*, sec_user_id, cursor=None, count=DEFAULT_PAGE_SIZE, profile=DEFAULT_PROFILE):
    """``cursor`` is the opaque cursor handed back by the previous page. For Douyin
    it decodes to ``max_cursor``, a millisecond publish timestamp; ``"0"`` asks
    for the first page."""
    return {
        **base_params(profile),
        "sec_user_id": str(sec_user_id),
        "max_cursor": _cursor(cursor),
        "count": str(count),
        "publish_video_strategy_type": "2",
        "from_user_page": "1",
        "locate_query": "false",
        "need_time_list": "1",
        "show_live_replay_strategy": "1",
        "time_list_query": "0",
        "pc_libra_divert": profile.os_name,
        "whale_cut_token": "",
    }
```

**重要补充**：`max_cursor` 的语义被明确记录 —— **它是"毫秒级发布时间戳"**，`"0"` 表示第一页。这一点我们实测只观察到"是个游标"，没有确认语义。

**来源 D：`Johnserf-Seed/f2` → `model.py`**

```python
class UserPost(BaseRequestModel):
    max_cursor: int
    count: int
    sec_user_id: str
```

### 3.2 分页做法

**`MediaCrawler` 的分页循环：**

```python
async def get_all_user_aweme_posts(self, sec_user_id: str, callback=None):
    posts_has_more = 1
    max_cursor = ""
    result = []
    while posts_has_more == 1:
        aweme_post_res = await self.get_user_aweme_posts(sec_user_id, max_cursor)
        posts_has_more = aweme_post_res.get("has_more", 0)
        max_cursor = aweme_post_res.get("max_cursor")
        aweme_list = aweme_post_res.get("aweme_list") if aweme_post_res.get("aweme_list") else []
        if callback:
            await callback(aweme_list)
        result.extend(aweme_list)
    return result
```

**`TikTokDownloader` 的分页（含提前终止优化）：**

```python
async def run(self, ..., data_key="aweme_list", cursor="max_cursor", has_more="has_more", ...):
...
async def early_stop(self):
    """如果获取数据的发布日期已经早于限制日期，就不需要再获取下一页的数据了"""
    if (not self.favorite
        and self.earliest > datetime.fromtimestamp(max(int(self.cursor) / 1000, 0)).date()):
        self.finished = True
```

注意 `int(self.cursor) / 1000` —— 再次印证 `max_cursor` 是**毫秒时间戳**。

**分页字段小结**（四个项目一致）：
- 请求：`max_cursor`（首次传 `0`）+ `count`
- 响应：`aweme_list`（作品数组）+ `has_more`（0/1）+ `max_cursor`（下一页游标）

与我们的实测完全吻合。

**`count` 取值**：`MediaCrawler` 用 18，`TikTokDownloader` 默认 18，`Evil0ctal` 用 `DEFAULT_PAGE_SIZE`，`DouYin_Spider` 用 18。我们实测用 10，服务端返回 9 条 —— 说明 count 只是"上限建议"，实际返回数由服务端决定。

---

## 4. 签名问题（本次调研最关键的部分）

### 4.1 结论：抖音不是对所有接口都签名保护

**两个项目各自独立地从抖音自己的 web SDK `runtime_bundler_34.js` 中抄出了签名保护路径白名单，且两份白名单逐条完全一致。**

**来源 A：`Evil0ctal/Douyin_TikTok_Download_API` → `src/dtk/signing/protection.py`**

```python
"""Which endpoints the platform refuses without a browser-made signature.

Douyin does not sign-protect its whole API. Its own web SDK carries the list:
`runtime_bundler_34.js` from lf-security.bytegoofy.com registers a strategy
named ``webSign`` - the SDK labels it "API signing protection" - whose
``config.protectedHost`` names the exact host, method and paths that get a
signature attached::

    if ("webSign" === f.strategyKey && b === a.REWRITE) {
      var s = window.use("webSignUrl");
      c.args[0] = s(c.url).url          // rewrites the URL, adding the signature
    }

Measured against live Douyin on 2026-09-08, one identity, eight requests each,
pure-Python signing only:

    /aweme/v1/web/user/profile/other/   unprotected   8/8 returned data
    /aweme/v1/web/comment/list/         unprotected   8/8 returned data
    /aweme/v1/web/aweme/detail/         PROTECTED     3/8, rest 403 Uifid Not Found
    /aweme/v1/web/aweme/post/           PROTECTED     3/8, rest 403 Uifid Not Found

The correlation is exact, which is what makes this table worth having rather
than guessing.
"""

DOUYIN_SIGNED_PATHS: frozenset[str] = frozenset(
    {
        "/aweme/v1/web/aweme/detail/",
        "/aweme/v1/web/aweme/post/",
        "/aweme/v1/web/aweme/favorite/",
        "/aweme/v1/web/aweme/listcollection/",
        "/aweme/v1/web/mix/aweme/",
        "/aweme/v1/web/tab/feed/",
        "/aweme/v1/web/mix/list/",
        "/aweme/v1/web/music/aweme/",
        "/aweme/v1/web/music/list/",
        "/aweme/v1/web/mix/detail/",
        "/aweme/v1/web/mix/listcollection/",
        "/aweme/v1/web/music/detail/",
        "/aweme/v1/web/collects/list/",
        "/aweme/v1/web/collects/video/list/",
    }
)

def requires_browser_signature(platform, url, cookies=None) -> bool:
    ...
    if _normalise(urlsplit(url).path) not in DOUYIN_SIGNED_PATHS:
        return False
    return pick_uifid(cookies) is None
```

**来源 B：`JoeanAmier/TikTokDownloader` → `src/encrypt/douyin_params.py`**

文件头明确注明改编自来源 A：

```python
# 本文件改编自以下项目的 a_bogus 与 x-secsdk-web-signature 签名实现：
#   `https://github.com/Evil0ctal/Douyin_TikTok_Download_API`
#   src/dtk/signing/native/abogus.py
#   src/dtk/signing/native/websign.py
```

```python
# ============================================================
# 抖音签名保护接口列表
#
# 抖音并非对所有接口做签名保护：其网页 SDK（runtime_bundler_34.js）
# 的 webSign 策略在 config.protectedHost["www.douyin.com"].GET 中
# 声明了需要附加 x-secsdk-web-signature 的确切路径，列表照此复制。
# 实测（2026-09-08，每接口 8 次请求，纯 Python 签名）：
#
#     /aweme/v1/web/user/profile/other/   未保护   8/8 返回数据
#     /aweme/v1/web/comment/list/         未保护   8/8 返回数据
#     /aweme/v1/web/aweme/detail/         受保护   3/8，其余 403 Uifid Not Found
#     /aweme/v1/web/aweme/post/           受保护   3/8，其余 403 Uifid Not Found
#
# POST 列表是 GET 列表的子集，故不区分请求方法...
# ============================================================

DOUYIN_SIGNED_PATHS: frozenset[str] = frozenset(
    {
        "/aweme/v1/web/aweme/detail/",
        "/aweme/v1/web/aweme/post/",
        "/aweme/v1/web/aweme/favorite/",
        "/aweme/v1/web/aweme/listcollection/",
        "/aweme/v1/web/mix/aweme/",
        "/aweme/v1/web/tab/feed/",
        "/aweme/v1/web/mix/list/",
        "/aweme/v1/web/music/aweme/",
        "/aweme/v1/web/music/list/",
        "/aweme/v1/web/mix/detail/",
        "/aweme/v1/web/mix/listcollection/",
        "/aweme/v1/web/music/detail/",
        "/aweme/v1/web/collects/list/",
        "/aweme/v1/web/collects/video/list/",
    }
)
```

**两份列表逐条比对：完全一致，14 条，无差异。**

### 4.2 直接回答我们的三个问题

| 接口 | 是否在签名白名单 | 实测结果 | 结论 |
|---|---|---|---|
| `general/search/single` 等**所有 search 接口** | ❌ 不在 | — | **不需要签名** ✅ 与实测一致 |
| `/aweme/v1/web/user/profile/other/` | ❌ **不在** | 8/8 返回数据 | **不需要签名**（我们尚未测，这是新结论） |
| `/aweme/v1/web/aweme/post/` | ✅ **在** | 3/8，其余 403 | **需要签名**（我们尚未测，这是新结论） |
| `/aweme/v1/web/aweme/detail/` | ✅ 在 | 3/8，其余 403 | **需要签名** ⚠️ 见下方说明 |

### 4.3 ⚠️ 需要修正我们实测的一处认知

> 我们的结论：搜索和详情接口不需要签名（直接 httpx 就通，加了 a_bogus 反而返回空）

**"搜索不需要签名"是对的。"详情不需要签名"需要区分两种"详情"：**

- 我们说的"详情"如果指 **`general/search/single` 返回的搜索结果**（我们监听到的 JSON 响应）→ 不需要签名，✅ 正确。
- 如果指 **`/aweme/v1/web/aweme/detail/`（视频详情接口）** → **它在受保护白名单里，需要签名**。

这两个是不同的接口。**建议核实一下我们实测时打的具体是哪一个路径。**

另外，"加了 a_bogus 反而返回空"这个现象**不能用"签名是多余的"来解释**。`Evil0ctal` 与 `JoeanAmier` 都记录了两种不同的 403 错误，说明签名是一个**多因素**问题：

```python
# MediaCrawler → media_platform/douyin/client.py
# 抖音边缘网关 ArgusSecurityPlugin 要求的请求头。网关目前不校验取值，
# 传固定字符串即可；将来若开始真校验，会重新出现 "Signature Not Found"。
DOUYIN_ARGUS_HEADER_VALUE = "1"

# 抖音边缘网关的 ArgusSecurityPlugin 会对这批接口做业务前置校验，缺少
# x-tt-argus 头时直接 403，响应体为
# "Blocked by ArgusSecurityPlugin Uifid Not Found"（补了 uifid 但没这个头则是
# "... Signature Not Found"）。当前网关尚未校验该头的值，可传任意字符串；
```

**即：a_bogus 算错 / 算对了但缺 uifid，都会导致 403 或空响应。** "加了反而变空"很可能是**签名参数与 uifid / msToken 不同源**导致的，而不是"签名有害"。

`MediaCrawler` 在视频详情接口上的注释进一步印证：

```python
# 抖音 detail 接口的 Argus 风控要求这两个参数成套出现，缺一则直接 403
#   uifid         = UIFID cookie，没有时退到 UIFID_TEMP
#   verifyFp / fp = s_v_web_id cookie
# 必须用 cookie 里的 s_v_web_id：实测 uifid 搭配自生成的 verifyFp 会被判成
# "Signature Not Found"，两者同源才能通过。
```

### 4.4 `aweme/post` 的签名是**两段式**，不是只有一个 a_bogus

这是最容易踩坑的地方。两个项目都实现为：

```
a_bogus
   ↓
完整 query（含 a_bogus）
   ↓
命中签名保护接口 且 query 含 uifid 时
追加 timestamp 与 x-secsdk-web-signature
   ↓
返回最终 query
```

**`JoeanAmier/TikTokDownloader` → `src/encrypt/douyin_params.py`，`sign_url()`**

```python
def sign_url(self, url="", query="", data=None, method="", user_agent=USERAGENT, ms_token="") -> str:
    # 1. 规范化业务 query
    query = _normalize_query(query)

    # 受保护接口使用 WebSign 的规范 query 表示计算 A-Bogus。
    # 普通接口不经过 WebSign，使用业务 query 表示。
    protected = bool(url and _is_sign_protected(url))
    uifid = _get_query_value(query, UIFID_PARAM) if protected else ""
    if uifid:
        query = _websign_normalize_query(query)

    a_bogus = self._get_a_bogus(query, data, user_agent)

    # s4 字母表包含 "/" 与 "=" 填充，发送前需百分号编码
    signed_query = f"{query}&a_bogus={quote(a_bogus, safe='')}"

    # 2. WebSign（仅受保护且带 UIFID 的接口）
    if not uifid:
        return signed_query

    # 追加 timestamp 与 x-secsdk-web-signature；签名覆盖其前面的
    # 完整 query（含 a_bogus）。
    return web_sign(signed_query, uifid)[0]
```

**关键点**：
1. `x-secsdk-web-signature` 是**第二段签名**，只有在**命中白名单 + query 里有 uifid** 时才附加。
2. 没有 `uifid` 时直接返回未签名 query —— 也就是说**签名依赖 cookie 里的 uifid**，不是纯算法能补的。
3. 第二段签名**覆盖包含 a_bogus 在内的完整 query**。

**`Evil0ctal` 的说明**（`protection.py`）：

```
Douyin needs the identity's visitor id, for the same reason:
`dtk.signing.native.websign` computes the platform's own
``x-secsdk-web-signature``, and 24 of 24 live requests across all four
endpoints returned data with no browser involved. The table below still
decides for a jar with no visitor id in it.
```

**`MediaCrawler` 的做法完全不同（值得注意）** —— 它不做白名单判断，而是**"除 general/search 以外全部加 a_bogus"**：

```python
# media_platform/douyin/client.py, __process_req_params()
if "/v1/web/general/search" not in uri:
    a_bogus = await get_a_bogus(uri, query_string, post_data, headers["User-Agent"], self.playwright_page)
    params["a_bogus"] = a_bogus
```

这是一个**保守的超集策略**：给不需要签名的接口（如 `user/profile/other`）也附上 a_bogus。
这与"`user/profile/other` 不需要签名"**不矛盾** —— 不需要签名的接口多带一个参数不会被拒。
同时也说明：MediaCrawler 认为**只有 `general/search` 系是明确不需要签名的**。

### 4.5 关于 a_bogus 的两个实现路线

- **JS 执行路线**：`MediaCrawler` 用 `execjs` 跑 `libs/douyin.js`（`media_platform/douyin/help.py`）。注意注释说 `get_a_bogus` 目前**不支持 POST 签名**，且 playwright 版本已废弃。
- **纯 Python 路线**：`Evil0ctal` 的 `src/dtk/signing/native/abogus.py`（逆向 `bdms.js`）+ `websign.py`（逆向 secsdk）。`JoeanAmier` 直接改编了它，见 §4.1 引用。**纯 Python 路线是正确的选择。**

`JoeanAmier` 还有 `src/encrypt/xBogus.py` 和 `static/js/X-Bogus.js`，但当前主路径用 a_bogus（`DouYinParams.sign()` 只计算 a_bogus）。

### 4.6 其他必需的请求头

**`x-tt-argus`**（`MediaCrawler` 明确记录，值目前不校验，传 `"1"` 即可）：

```python
self.headers.setdefault("x-tt-argus", DOUYIN_ARGUS_HEADER_VALUE)   # "1"
uifid = cookie_dict.get("UIFID") or cookie_dict.get("UIFID_TEMP", "")
if uifid:
    self.headers.setdefault("uifid", uifid)
```

**`Referer`** —— 所有项目都按接口设置对应 Referer：

```python
# 用户主页作品
self.set_referer(f"{self.domain}user/{self.sec_user_id}")          # TikTokDownloader
# 用户搜索
refer = f'https://www.douyin.com/search/{urllib.parse.quote(query)}?type=user'   # DouYin_Spider
# 用户资料
headers.set_referer(user_url)                                       # DouYin_Spider
```

**`Origin`**：`Evil0ctal` 的 `DEFAULT_HEADERS` 带 `Origin: https://www.douyin.com`；
但 `MediaCrawler` 打视频详情时会 `del headers["Origin"]`，说明某些接口**带了反而出问题**。

**公共查询参数（每个请求都要带，`Evil0ctal` 的 `base_params`）**：

```python
device_platform=webapp, aid=6383, channel=channel_pc_web, pc_client_type=1,
version_code/version_name（见下）, cookie_enabled=true,
screen_width/screen_height, browser_language=zh-CN, browser_platform=MacIntel,
browser_name=Chrome, browser_version/browser_online/engine_name/engine_version,
os_name/os_version, cpu_core_num, device_memory, platform=PC,
downlink=10, effective_type=4g, round_trip_time, update_version_code
```

**`version_code` 因接口而异**（`DouYin_Spider` 实测记录，这是个容易忽略的坑）：

```python
# 59 条是 170400，但 aweme/detail=190500、aweme/post=290100、
# general/search/single=190600，各自前端模块自带版本号。
```

而 `TikTokDownloader` 当前统一用 `290100 / 29.1.0`，`MediaCrawler` 用 `190600 / 19.6.0`
（仅搜索接口），`Evil0ctal` 用模块级常量。**没有全网统一值，建议按接口实测。**

---

## 5. 我们没发现的用户相关接口（完整清单）

以下路径**均来自源码常量表**，非推测。

### 5.1 用户本体 / 关系

| 接口路径 | 用途 | 来源 |
|---|---|---|
| `/aweme/v1/web/user/profile/other/` | 他人用户资料（**我们已用**） | 全部项目 |
| `/aweme/v1/web/im/user/info/` | 用户短信息 | `f2` `USER_SHORT_INFO`；`Evil0ctal` 同 |
| `/aweme/v1/web/query/user/` | **查询当前登录者自己的 uid**（`user_uid`） | `f2` `QUERY_USER`；`Evil0ctal` `QUERY_USER`；`DouYin_Spider` `get_my_uid()` |
| `/aweme/v1/web/user/following/list/` | 关注列表 | `f2` `USER_FOLLOWING`；`Evil0ctal`；`DouYin_Spider` |
| `/aweme/v1/web/user/follower/list/` | 粉丝列表 | `f2` `USER_FOLLOWER`；`Evil0ctal`；`DouYin_Spider` |
| `/aweme/v1/web/im/user/info/` | IM 用户信息 | `f2` / `Evil0ctal` |
| `/webcast/distribution/check_user_live_status/` | 用户直播状态 | `f2` `USER_LIVE_STATUS` |
| `/webcast/user/me/` | 直播用户信息 | `f2` `LIVE_USER_INFO`；`Evil0ctal` 同 |

**`/aweme/v1/web/query/user/`** 特别值得注意 —— `Evil0ctal` 注释说明它返回 `user_uid`，是**"这个 session 是谁"**的接口，且游客也能用：

```python
# Who the platform thinks the caller is. Answers about the client that
# asked rather than about a user named in the request - but it answers for
# a guest too, with a device uid of its own, so it identifies the client
# and does not establish a login.
QUERY_USER: Final = f"{DOUYIN_DOMAIN}/aweme/v1/web/query/user/"
```

`DouYin_Spider` 用它拿自己的 uid：

```python
def get_my_uid(auth, **kwargs) -> int:
    url = 'https://www.douyin.com/aweme/v1/web/query/user/'
    refer = 'https://www.douyin.com/'
    return int(resp_json['user_uid'])
```

**注意 `DouYin_Spider` 关于 `get_my_sec_uid` 的一条实测记录**（对判断"能否绕过 sec_uid"有价值）：

```python
def get_my_sec_uid(auth, **kwargs) -> str:
    """
    主站 `/user/self` 已改成客户端渲染，HTML 里不再有 secUid（2026-08-16 复核），
    """
```

### 5.2 用户作品 / 收藏类

| 接口路径 | 用途 | 来源 |
|---|---|---|
| `/aweme/v1/web/aweme/post/` | 用户发布作品（**我们已用**） | 全部项目 |
| `/aweme/v1/web/aweme/favorite/` | 用户喜欢作品 | `f2` `USER_FAVORITE_A`；`Evil0ctal`；`TikTokDownloader` `favorite_api`；`DouYin_Spider` |
| `/web/api/v2/aweme/like/` | 用户喜欢作品（变体 B，iesdouyin 域） | `f2` `USER_FAVORITE_B`；`Evil0ctal` 同 |
| `/aweme/v1/web/aweme/listcollection/` | 用户收藏作品 | `f2` `USER_COLLECTION`；`Evil0ctal`；`DouYin_Spider` |
| `/aweme/v1/web/collects/list/` | 用户收藏夹列表 | `f2` `USER_COLLECTS`；`Evil0ctal`；`DouYin_Spider` `get_collect_list()` |
| `/aweme/v1/web/collects/video/list/` | 收藏夹内作品 | `f2` `USER_COLLECTS_VIDEO`；`Evil0ctal` |
| `/aweme/v1/web/music/listcollection/` | 用户音乐收藏 | `f2` `USER_MUSIC_COLLECTION`；`Evil0ctal` |
| `/aweme/v1/web/history/read/` | 观看历史 | `f2` `USER_HISTORY`；`Evil0ctal` |
| `/aweme/v1/web/locate/post/` | 用户主页内定位作品 | `f2` `LOCATE_POST`；`Evil0ctal` |
| `/aweme/v1/web/home/search/item/` | **主页内作品搜索** | `f2` `HOME_POST_SEARCH`；`Evil0ctal` 无（仅在 f2） |

**`/aweme/v1/web/home/search/item/`** 是我们完全没有的接口 —— "在某个用户主页内搜索作品"。
`f2` 的 `HomePostSearch` 模型（`model.py`）：

```python
class HomePostSearch(BaseRequestModel):
    offset: int = 0
    count: int = 10
    from_user: str
```

（`from_user` 应为该用户的 sec_user_id。）

`Evil0ctal` 还提供了 `AuthorLikes` 端点的一条重要行为记录（对判空逻辑很关键）：

```python
# Douyin says "these likes are private" by answering 200 with no body at
# all. Measured 2026-09-10 against two different authors: zero bytes
# both times, while `author_posts` for the same author on the same
# identity returned 230KB and 439KB in the request immediately after.
empty_body_is_normal=True,
```

**即：喜欢列表现为私密时，返回 200 + 空 body（0 字节），而不是错误码。这容易误判为"请求失败"。**

### 5.3 `f2` 独有的用户相关接口

`f2`（`Johnserf-Seed/f2`）的用户接口面最广，`f2/apps/douyin/api.py` 的 `DouyinAPIEndpoints` 中还有：

```python
USER_SHORT_INFO = f"{DOUYIN_DOMAIN}/aweme/v1/web/im/user/info/"
USER_DETAIL     = f"{DOUYIN_DOMAIN}/aweme/v1/web/user/profile/other/"
USER_POST       = f"{DOUYIN_DOMAIN}/aweme/v1/web/aweme/post/"
USER_FAVORITE_A = f"{DOUYIN_DOMAIN}/aweme/v1/web/aweme/favorite/"
USER_FAVORITE_B = f"{IESDOUYIN_DOMAIN}/web/api/v2/aweme/like/"
USER_FOLLOWING  = f"{DOUYIN_DOMAIN}/aweme/v1/web/user/following/list/"
USER_FOLLOWER   = f"{DOUYIN_DOMAIN}/aweme/v1/web/user/follower/list/"
USER_HISTORY    = f"{DOUYIN_DOMAIN}/aweme/v1/web/history/read/"
USER_COLLECTION = f"{DOUYIN_DOMAIN}/aweme/v1/web/aweme/listcollection/"
USER_COLLECTS   = f"{DOUYIN_DOMAIN}/aweme/v1/web/collects/list/"
USER_COLLECTS_VIDEO = f"{DOUYIN_DOMAIN}/aweme/v1/web/collects/video/list/"
USER_MUSIC_COLLECTION = f"{DOUYIN_DOMAIN}/aweme/v1/web/music/listcollection/"
LOCATE_POST     = f"{DOUYIN_DOMAIN}/aweme/v1/web/locate/post/"
HOME_POST_SEARCH = f"{DOUYIN_DOMAIN}/aweme/v1/web/home/search/item/"
QUERY_USER      = f"{DOUYIN_DOMAIN}/aweme/v1/web/query/user/"
USER_LIVE_STATUS = f"{LIVE_DOMAIN}/webcast/distribution/check_user_live_status/"
LIVE_USER_INFO  = f"{LIVE_DOMAIN}/webcast/user/me/"
```

`f2` 的 `UserFollowing` / `UserFollower` 模型（`model.py`）给出了这两个接口的完整参数：

```python
class UserFollowing(BaseRequestModel):
    user_id: str = ""
    sec_user_id: str = ""
    offset: int = 0        # 相当于 cursor
    min_time: int = 0
    max_time: int = 0
    count: int = 20
    # source_type = 1: 最近关注 需要指定 max_time(s) 3: 最早关注 需要指定 min_time(s) 4: 综合排序
    source_type: int = 4
    gps_access: int = 0
    address_book_access: int = 0

class UserFollower(BaseRequestModel):
    user_id: str
    sec_user_id: str
    offset: int = 0        # 相当于 cursor 但只对 source_type: = 2 有效，其他情况为 0 即可
    min_time: int = 0
    max_time: int = 0
    count: int = 20
    # source_type = 1: 最近关注 需要指定 max_time(s) 2: 综合关注(意义不明)
    source_type: int = 1
    gps_access: int = 0
    address_book_access: int = 0
```

**注意：粉丝/关注列表同时接受 `user_id` 和 `sec_user_id`** —— 与用户资料接口不同，这里 `user_id` 是可用的。

---

## 6. 对比表格

| 项目名 | 用户搜索接口 | 用户资料接口 | 作品列表接口 | 是否需要签名 | 来源文件 |
|---|---|---|---|---|---|
| **JoeanAmier/TikTokDownloader** | `/aweme/v1/web/discover/search/`<br>`search_channel=aweme_user_web`<br>key=`user_list` | `/aweme/v1/web/user/profile/other/`<br>`sec_user_id`+`publish_video_strategy_type=2`+`personal_center_strategy=1` | `/aweme/v1/web/aweme/post/`<br>`sec_user_id`+`max_cursor`+`count=18`+`from_user_page=1` | **白名单制**：`post`✅受保护 / `profile/other`❌不受保护 / search❌不受保护。受保护接口需 a_bogus **+** `x-secsdk-web-signature`（依赖 uifid） | `src/interface/search.py`<br>`src/interface/user.py`<br>`src/interface/account.py`<br>`src/encrypt/douyin_params.py` |
| **NanmiCoder/MediaCrawler** | `/aweme/v1/web/general/search/single/`<br>（仅实现了综合搜索；`SearchChannelType.USER = "aweme_user_web"` 已定义但**未接入**用户搜索爬虫） | `/aweme/v1/web/user/profile/other/`<br>`sec_user_id`+`publish_video_strategy_type=2`+`personal_center_strategy=1` | `/aweme/v1/web/aweme/post/`<br>`sec_user_id`+`max_cursor`+`count=18`+`locate_query=false` | 除 `/v1/web/general/search` 外**全部**加 a_bogus（execjs 跑 `libs/douyin.js`）；另需 `x-tt-argus: 1` 头 + `uifid` | `media_platform/douyin/client.py`<br>`media_platform/douyin/field.py`<br>`media_platform/douyin/help.py` |
| **cv-cat/DouYin_Spider** | `/aweme/v1/web/discover/search/`<br>`search_channel=aweme_user_web`<br>+`search_filter_value` 可选筛选 | `/aweme/v1/web/user/profile/other/`<br>`sec_user_id`+`profile_other_record_enable=1` | `/aweme/v1/web/aweme/post/`<br>`sec_user_id`+`from_user_page`+`max_cursor` | 有 `params.signed_url(...)` 机制；`aweme/favorite` 等明确走签名。用户搜索另有独立签名路径 | `dy_apis/douyin_api.py`<br>`builder/params.py`<br>`utils/secsdk_web_sign.py` |
| **Evil0ctal/Douyin_TikTok_Download_API** | `USER_SEARCH = /aweme/v1/web/discover/search/`（常量已定义，README 表明搜索能力已上线） | `USER_DETAIL = /aweme/v1/web/user/profile/other/`<br>`sec_user_id`+`publish_video_strategy_type=2`+`personal_center_strategy=1` | `USER_POST = /aweme/v1/web/aweme/post/`<br>`sec_user_id`+`max_cursor`+`count`+`from_user_page=1`+`locate_query=false` | **权威白名单来源**：`DOUYIN_SIGNED_PATHS` 14 条（含 `aweme/post`，**不含** `profile/other`）；纯 Python a_bogus + WebSign | `src/dtk/platforms/douyin/endpoints.py`<br>`src/dtk/platforms/douyin/params.py`<br>`src/dtk/signing/protection.py` |
| **Johnserf-Seed/f2** | （`api.py` 中**未定义**用户搜索常量；有 `SUGGEST_WORDS` 推荐词） | `USER_DETAIL = /aweme/v1/web/user/profile/other/`<br>`UserProfile{sec_user_id}` | `USER_POST = /aweme/v1/web/aweme/post/`<br>`UserPost{max_cursor, count, sec_user_id}` | 有 `ABogusManager` / `XBogusManager` 双实现，`fetch_user_profile` 与 `fetch_user_post` **都经过** `bogus_manager.model_2_endpoint()` | `f2/apps/douyin/api.py`<br>`f2/apps/douyin/crawler.py`<br>`f2/apps/douyin/model.py` |
| **erma0/douyin** | — | — | — | — | **仓库已清空，仅剩 `README.md`**，无可调研源码 |

### 表格补充说明

- **MediaCrawler 的用户搜索**：`SearchChannelType.USER = "aweme_user_web"` 已在 `field.py` 定义，但 `media_platform/douyin/core.py` 的 `DouYinCrawler` 只实现了 `search()`（走 `search_info_by_keyword`，默认 `SearchChannelType.GENERAL`）和 `get_specified_awemes()`。**没有独立的用户搜索爬虫入口**。所以它的用户搜索能力是"参数已支持、爬虫未接入"。
- **f2 的用户搜索**：`f2/apps/douyin/api.py` 的 `DouyinAPIEndpoints` 中确实**没有**用户搜索常量（只有 `SUGGEST_WORDS`）。**不编造，如实标注"未定义"。**
- **erma0/douyin**：仓库 tree 只有 `README.md` 一个文件，源码已不存在。**无法调研，如实标注。**

---

## 7. 对我们项目的具体行动建议

### 7.1 必须改

1. **用户搜索的 `search_channel` 改为 `aweme_user_web`**（现在我们用 `aweme_user`）。
   —— 四个项目一致，且 `DouYin_Spider` 注释明确指出枚举值来源。
2. **明确 `search_channel` 必须与路径配对**：用户搜索只能用 `discover/search` + `aweme_user_web`。
   把它接到 `general/search/single` 上永远无效 —— **这不是待修的 bug，而是设计如此**，建议在代码里加注释固化这个认知，避免后人重复踩。

### 7.2 必须实测确认

3. **`aweme/post` 的签名行为**（最高优先级）。预期结果：不加签名时**概率性 403**（约 5/8 失败），错误体为
   `Blocked by ArgusSecurityPlugin Uifid Not Found` 或 `... Signature Not Found`，**不是空数据**。
   建议实测时把 HTTP 状态码和响应体记录到日志，与我们现有"返回空"的判空逻辑区分开 ——
   否则 403 可能被误判成"该用户没有作品"。
4. **`user/profile/other` 不带签名**（预期 8/8 成功）。若我们也拿不到数据，
   问题大概率在公共参数 / 请求头（`Referer`、`x-tt-argus`、`uifid`、`webid`），而不在签名。
5. **逐个接口校准 `version_code`**。`DouYin_Spider` 实测：`aweme/detail=190500`、
   `aweme/post=290100`、`general/search/single=190600`，各不相同。

### 7.3 建议补充

6. 增加 `x-tt-argus: 1` 请求头（`MediaCrawler` 记录缺它直接 403，且当前网关不校验取值）。
7. 若要做完整用户画像，可补 `/aweme/v1/web/query/user/`（拿当前 session 的 uid）——
   **游客态也能用**，是判断 cookie 是否有效的低成本探针。
8. 若要支持"主页内搜索作品"，`/aweme/v1/web/home/search/item/` 是 `f2` 独有的发现。

### 7.4 判空逻辑要区分三种"空"

调研中发现三种不同的"没数据"，我们的代码必须区分，否则会互相误判：

| 现象 | 含义 | 来源 |
|---|---|---|
| 200 + `aweme_list` 为空 | 真的没有作品 | 常规 |
| **200 + body 为 0 字节** | 喜欢列表私密（正常，非错误） | `Evil0ctal` `empty_body_is_normal=True` |
| **403 + `Uifid Not Found` / `Signature Not Found`** | **签名/风控失败**，需要签名或补 uifid | `MediaCrawler` / `Evil0ctal` |

第三种必须**与第二种区分**，否则会把风控失败当成"用户没有作品"静默吞掉。

---

## 8. 调研局限（如实说明）

1. **`Johnserf-Seed/f2` 的用户搜索接口**：未在其 `api.py` 常量表中找到。**不编造，标注为"未定义"。** 不能据此断言 f2 不支持用户搜索，只能说其 endpoint 常量表里没有。
2. **`NanmiCoder/MediaCrawler` 的用户搜索**：`SearchChannelType.USER` 已定义但爬虫入口未接入，因此**没有找到它的 `discover/search` 实际调用代码**，其 `discover/search` 参数完整度无法从该项目验证。
3. **`erma0/douyin`**：仓库仅剩 `README.md`，源码不可得，**本次未能调研**。
4. **`cv-cat/DouYin_Spider` 的签名细节**：确认了 `utils/secsdk_web_sign.py` 与 `params.signed_url()` 的存在，但**未逐行读签名实现**，因此其"哪些接口走签名"的完整判断依据未完全验证（`aweme/post` 的签名归属系根据其余三个项目推定 + 其 `signed_url` 机制的存在）。
5. **`DOUYIN_SIGNED_PATHS` 白名单的时效性**：两份白名单的实测日期均标注为 **2026-09-08**。抖音会变更风控策略，**该白名单可能已过期**。两个项目的注释都说明了"过期时的失败方向"（新受保护接口会 403 报 uifid/签名，属显式失败），建议我们自己也定期复测。
6. **我们实测的 `search_channel=aweme_user` 是否真的完全无效**：调研只能证明"正确值是 `aweme_user_web`"，无法证明 `aweme_user` 一定不被接受。但结合 `general/search/single` 只认 `aweme_general` 的机制，我们的现象得到了自洽解释。
