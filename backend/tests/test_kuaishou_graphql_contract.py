"""快手取博主资料的**契约**测试（不联网）。

## 最终方案（2026-10-11，从那份独立调查的脚本反推出来的）

**`profile/user` + 借用 `profile/get` 的签名。**

### 证据链

1. 那份调查拿到的是**精确值**（fan:12548 / like:55165）+ 昵称/简介，
   做法写在它的 `e_profileuser.js` 里：
   ```js
   const sig = 'HUDR_sFnX-DtsGEFXsbDPT3TMP-sk0is6A6ZH7E4…';   // 硬编码现成签名
   const url = '…/profile/user?__NS_hxfalcon=' + sig + '&caver=2';
   ```
   **它没有从 `profile/user` 抓签名**（页面根本不发那个路径），
   而是**拿现成签名改了路径** —— 快手接受了。

2. 线上日志证明 `profile/get` 的签名**抓得到**：
   `抓到 3 个路径的签名：/rest/v/profile/get, /rest/v/search/feed, /rest/v/search/user`

3. 线上日志同时证明 `profile/get` **只返回登录账号自己** ——
   即使正确拼上 `?userId=` 也一样：
   `追加查询参数 → …（最终参数名：__NS_hxfalcon,caver,userId）`
   `profile/get 返回 2695872552 ≠ 请求的 3xep6p7wbnqcvj6`

⇒ 所以：**能抓到签名的路径（profile/get）借签名 + 能返回目标用户的路径
   （profile/user）**，两者组合。

### ⚠️ 这条推翻了本项目一条老结论

"签名绑路径 —— 用 A 的签名调 B → `result:2`"（2026-09-30 实测）
**至少不适用于 profile/user**（否则那份精确数据拿不到）。

### 为什么值得做

| | GraphQL（之前的兜底） | profile/user（现在） |
|---|---|---|
| 粉丝 | 四舍五入 `13000`（真实 12548） | **精确 12548** |
| 获赞 | **没有该字段** | **55165** |
| 昵称/头像/简介 | 没有 | 有 |

⚠️ **但这条尚未在本项目里跑通验证** —— 是"有强证据的尝试"，
   失败会自动退 GraphQL，不会让功能不可用。
"""
from __future__ import annotations

import inspect
import re


def _impl_source() -> str:
    from app.services.platforms.kuaishou.client import KuaishouClient

    return inspect.getsource(KuaishouClient._get_user_profile_impl)


def _helper_source() -> str:
    from app.services.platforms.kuaishou.client import KuaishouClient

    return inspect.getsource(KuaishouClient._post_profile_user)


# =============================================================================
# 主路径：profile/user + 借签名
# =============================================================================

def test_uses_profile_user_with_borrowed_signature():
    """★ 必须调 `profile/user`，且**借用别的路径的签名**。

    ⚠️ `profile/user` 页面从不请求 ⇒ 永远抓不到"它自己的"签名；
       必须像那份调查那样**改路径复用**。
    """
    src = _impl_source()
    assert "PROFILE_USER" in src, "应用 profile/user（唯一能返回目标用户资料的）"
    assert "PROFILE_GET" in src, "应把 profile/get 作为**借签名**的来源"
    assert "_post_profile_user" in src, "应走借签名的专用方法"


def test_helper_rewrites_path_keeps_signature():
    """借签名的实现：**换路径、留签名**。"""
    src = _helper_source()
    assert "PROFILE_USER" in src, "要把路径换成 profile/user"
    assert "__NS_hxfalcon" in src or "re.sub" in src, "要保留签名串（只换路径）"
    assert '"user_id": uid' in src or "user_id" in src, (
        "body 要带 user_id（且只吃 URL 字符串 id）"
    )


def test_helper_validates_user_id():
    """必须校验 `user_id == 目标 uid`，避免拿到登录账号自己的数据。"""
    src = _helper_source()
    assert 'prof.get("user_id")' in src, "缺少 user_id 校验"
    assert "≠ 请求的" in src, "身份不符时应记录并丢弃"


def test_parses_owner_count_fields():
    """解析 `ownerCount` 的四个字段（这份响应是嵌套结构）。

    实测真实响应：
        ownerCount = {fan:12548, like:55165, follow:8, photo_public:176}
    ⚠️ 注意 `like`（获赞）**只有这条能拿到**，GraphQL 没有该字段。
    """
    src = _helper_source()
    for f in ('oc.get("fan")', 'oc.get("follow")',
              'oc.get("photo_public")', 'oc.get("like")'):
        assert f in src, f"缺字段 {f}"
    # 身份字段来自 profile 的嵌套结构
    for f in ('prof.get("user_name")', 'prof.get("headurl")',
              'prof.get("user_text")'):
        assert f in src, f"缺身份字段 {f}"


def test_falls_back_to_graphql():
    """借签名失败时**退 GraphQL**，不能让功能不可用。

    ⚠️ 这条新路径**尚未在本项目验证过**，所以兜底是必需的。
    """
    src = _impl_source()
    assert "visionProfile" in src, "应保留 GraphQL 兜底"
    assert "_parse_cn_count" in src, 'GraphQL 的 fan 是 "1.3万" 这类字符串'
    assert '"photo": _parse_cn_count(oc.get("photo_public"))' in src, (
        "GraphQL 兜底也要用 photo_public —— 实测 photo 返回 null"
    )


def test_does_not_read_init_state():
    """⚠️ `INIT_STATE` 是**搜索页缓存残留**，不是该页数据（独立实测证伪）。"""
    src = _impl_source()
    assert "_read_profile_from_init_state" not in src, (
        "INIT_STATE 已被证伪：SSR HTML 里 8 个关键词全 0 命中，"
        "全量抓包里该页从未发出资料请求，且数值会漂移"
    )


def test_does_not_use_bare_profile_get():
    """⚠️ **不能**只靠 `profile/get` 取目标用户 —— 它只返回登录账号自己。

    线上日志（带正确 `?userId=` 也一样）：
        追加查询参数 → …（最终参数名：__NS_hxfalcon,caver,userId）
        profile/get 返回 2695872552 ≠ 请求的 3xep6p7wbnqcvj6
    """
    src = _impl_source()
    assert "extra_query=f\"userId={uid}\"" not in src, (
        "不要再用 profile/get + userId —— 实测它仍返回登录账号自己"
    )


# =============================================================================
# 签名的获取
# =============================================================================

def test_pages_for_tries_multiple_pages():
    """`_pages_for(uid)` 必须返回**多个**候选页面（凑齐不同路径的签名）。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._pages_for)
    assert "BASE}/profile/{uid}" in src, "应包含目标主页"
    assert "search_page_url" in src, "应同时包含搜索页"


def test_videos_passes_uid_for_signature():
    """`profile/feed` 的签名**只在目标主页**发出 ⇒ `_post` 必须传 uid。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient.get_user_videos)
    i = src.find("PROFILE_FEED,")
    assert i != -1, "没找到 profile/feed 调用"
    assert "uid=uid" in src[i:i + 200], "profile/feed 调 _post 必须传 uid"


def test_post_retries_on_navigation_destroy():
    """**回归**：`evaluate` 被导航打断时要**重试**（2026-10-10 线上 bug）。"""
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
    """headless 应**可配置**，注释里**不许把未证实的结论写成定论**。"""
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
