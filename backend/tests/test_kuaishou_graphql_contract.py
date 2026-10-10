"""快手取博主资料的**契约**测试（不联网）。

## 最终方案的由来（三次修正，每次都有实测依据）

**当前做法**：`GET /rest/v/profile/get?userId=<URL 字符串 id>`，
签名从「目标主页 / 搜索页」抓。

### 为什么不是 `POST /rest/v/profile/user`

独立调查报告实测它带 cookie 能返回完整资料，我据此改过一次。
**但线上日志证明它不可用**：

    抓到 4 个路径的签名：/rest/v/profile/feed, /rest/v/profile/get,
                        /rest/v/search/feed, /rest/v/search/user
    抓到签名但 /rest/v/profile/user **不在其中** → 500

⇒ **快手页面根本不发这个路径**，签名永远抓不到。
   （我已同时打开主页和搜索页，四个页面都没有它。）
⇒ **"这个接口能返回数据" ≠ "我们能调它"** —— 前提是能拿到它的签名。
   这是本轮最贵的一课。

### 为什么 `profile/get` 又可以了

它以前被判"只能查自己"，原因是**参数位置错了**：
独立实测是 `?userId=<id>`（**query**），而本项目历史上只发空 body、
不带 query ⇒ 拿回的永远是登录账号自己（日志 `ids=['2695872552']`）。

⇒ 现在：**能抓到签名的接口（profile/get）+ 正确的 `?userId=`**。

### 字段（`get_self_profile` 实测的顶层扁平结构）

    userId / userDefineId / userName / userHead / fans / follows / like / userTex

⚠️ 注意是 `fans` / `follows` / `like`，
**不是** GraphQL 的 `fan` / `follow` / `photo_public`。
"""
from __future__ import annotations

import inspect
import re


def _impl_source() -> str:
    from app.services.platforms.kuaishou.client import KuaishouClient

    return inspect.getsource(KuaishouClient._get_user_profile_impl)


# =============================================================================
# 主路径
# =============================================================================

def test_uses_profile_get_with_userid_query():
    """★ 必须调 `profile/get` **并带 `?userId=`**（两半缺一不可）。

    · 只用 `profile/get` 不带 userId → 返回的是**登录账号自己**
      （历史日志实测 `ids=['2695872552']`）
    · 只用 `profile/user` → **抓不到签名**，线上 500（见模块 docstring）
    """
    src = _impl_source()
    assert "PROFILE_GET" in src, "应用 profile/get（它的签名抓得到）"
    assert "extra_query=f\"userId={uid}\"" in src, (
        "必须带 ?userId= —— 否则拿回的是登录账号自己"
    )
    assert "PROFILE_USER" not in src, (
        "不要用 profile/user —— 线上日志证明**页面不发该路径**，签名抓不到"
    )


def test_does_not_read_init_state():
    """⚠️ `INIT_STATE` 是**搜索页缓存残留**，不是该页数据（独立实测证伪）。"""
    src = _impl_source()
    assert "_read_profile_from_init_state" not in src, (
        "INIT_STATE 已被证伪：SSR HTML 里 8 个关键词全 0 命中，"
        "全量抓包里该页从未发出资料请求，且数值会漂移"
    )


def test_profile_get_ranked_before_graphql():
    """`profile/get` 应排在 GraphQL 兜底**之前**（数字精确、且含获赞）。"""
    src = _impl_source()
    call = "profile = await self._post("
    assert call in src, "找不到 profile/get 调用"
    i_get = src.index(call)
    i_gql = src.index("--- 兜底：GraphQL")
    assert i_get < i_gql, "profile/get 必须优先于 GraphQL 兜底"


def test_field_names_match_profile_get():
    """字段名用 `fans`/`follows`/`like`（profile/get 的顶层扁平结构）。

    ⚠️ 别和 GraphQL 的 `fan`/`follow`/`photo_public` 搞混 —— 两套不一样。
    """
    src = _impl_source()
    for f in ('profile.get("fans")', 'profile.get("follows")',
              'profile.get("like")', 'profile.get("userName")'):
        assert f in src, f"缺字段 {f}（profile/get 的顶层字段）"


def test_profile_get_validates_user_define_id():
    """必须校验 `userDefineId == 目标 uid`，避免拿到登录账号自己的数据。"""
    src = _impl_source()
    assert 'profile.get("userDefineId")' in src, "缺少 userDefineId 校验"
    assert "≠ 请求的" in src, "身份不符时应记录并丢弃"


# =============================================================================
# 签名的获取
# =============================================================================

def test_pages_for_tries_multiple_pages():
    """`_pages_for(uid)` 必须返回**多个**候选页面。

    线上日志证明单开主页只有 feed+get；搜索页另有 search/feed+search/user。
    多列候选才能凑齐不同路径的签名（循环是"抓到目标就停"）。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._pages_for)
    assert "BASE}/profile/{uid}" in src, "应包含目标主页（唯一发 profile/feed 的）"
    assert "search_page_url" in src, "应同时包含搜索页"


def test_videos_passes_uid_for_signature():
    """`profile/feed` 的签名**只在目标主页**发出 ⇒ `_post` 必须传 uid。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient.get_user_videos)
    i = src.find("PROFILE_FEED,")
    assert i != -1, "没找到 profile/feed 调用"
    assert "uid=uid" in src[i:i + 200], "profile/feed 调 _post 必须传 uid"


def test_post_retries_on_navigation_destroy():
    """**回归**：`evaluate` 被导航打断时要**重试**（2026-10-10 线上 bug）。

    日志：`Page.evaluate: Execution context was destroyed,
           most likely because of a navigation.`
    ⇒ 抓签名会 `goto`，并发/翻页时把另一次 evaluate 的上下文销毁。
      加重试后线上验证通过（`作品 -> 20 条`）。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._post)
    assert "Execution context was destroyed" in src, "未识别该错误"
    assert "for attempt in range(" in src, "没有重试循环"


def test_signature_cache_key_matches_between_store_and_read():
    """**回归**：签名的「存」与「取」必须同键（2026-10-07 线上 bug）。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._ensure_signed_url)
    assert 'cache_key = f"{conn}:{uri}"' in src, "cache_key 不该带 uid"
    assert 'f"{conn}:{path}"' in src, "写入缓存的键也不该带 uid"
    assert "_signed_urls.get(cache_key)" in src, "读取应统一用 cache_key"


def test_headless_configurable_without_asserting_conclusion():
    """headless 应**可配置**，注释里**不许把未证实的结论写成定论**。

    2026-10-10 我先测出"无头失败"、改成有头，**随后又测出无头成功**，
    两次自相矛盾 ⇒ 该结论未复现，不该据此改变默认行为（会弹用户窗口）。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._get_session)
    assert "YLCRAFT_KS_HEADLESS" in src, "headless 应可通过环境变量配置"

    prose = re.sub(r"#.*", "", src)
    prose = re.sub(r'""".*?"""', "", prose, flags=re.S)
    for wrong in ("无头一定不行", "无头必然抓不到", "无头一定行"):
        assert wrong not in prose.replace("**", ""), (
            f"注释里有断言式说法 {wrong!r} —— 未复现的结论不能写成定论"
        )
    assert 'YLCRAFT_KS_HEADLESS", "1"' in prose, "默认应保持无头"
