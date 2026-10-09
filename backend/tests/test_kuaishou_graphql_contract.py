"""快手 GraphQL 取博主统计的**契约**测试（不联网、不需要浏览器）。

## 实测确认的事实（2026-10-07，多次抓包 + GraphQL 报错校准）

参考开源项目 MediaCrawler 的
`media_platform/kuaishou/graphql/vision_profile.graphql`，实测快手博主资料走
**GraphQL**（不是 REST）：

    POST https://www.kuaishou.com/graphql
    {
      "query": "query{ visionProfile(userId:\\"<uid>\\"){ result "
               "userProfile{ ownerCount{ fan photo follow } } } }"
    }

字段靠 GraphQL 的 `Did you mean` 报错试出来（introspection 被禁）：

| 试的东西                  | 结果                                              |
|---------------------------|---------------------------------------------------|
| `visionProfileUser`       | 不存在；报错列出 visionProfile / visionProfileUserList / … |
| 参数 `id` / `user_id`     | 不认，只认 **`userId`**                          |
| `userProfile{ fan }`      | ✗ → `Did you mean "ownerCount"?`                 |
| `ownerCount{ fan photo follow }` | ✓✓✓ **三个都存在**                       |
| `ownerCount{ like/video/note/total }` | ✗ 都不存在                |
| `userProfile{ name/headurl/userText/id/verified }` | ✗ **全部不存在**         |
| `likedCount` / `photoCount` / `fanCount` | ✗ **全不存在**               |

⚠️ **没有「获赞」字段** —— 页面上那个「获赞 5.5万」不在这条通道里。

⚠️ GraphQL 的 `visionProfile(userId:…)` **自带 userId 参数**，
所以它查的就是**目标用户**，不需要先跳转页面（见下方测试）。

## 这些测试的作用

防止再有人（包括我）按 REST 的直觉去猜字段 —— 那些字段**一个都不存在**。
另外还钉住了两次线上事故的教训（详见各测试 docstring）。
"""
from __future__ import annotations

import inspect
import re


def _impl_source() -> str:
    from app.services.platforms.kuaishou.client import KuaishouClient

    return inspect.getsource(KuaishouClient._get_user_profile_impl)


# =============================================================================
# 查询形态
# =============================================================================

def test_uses_graphql_endpoint():
    """必须打 `/graphql`，不是 REST 的 `/rest/v/profile/get`。"""
    src = _impl_source()
    assert "/graphql" in src, "没走 GraphQL 端点"
    assert "visionProfile" in src, "没调用 visionProfile 查询"


def test_queries_owner_count_fields():
    """必须查 `ownerCount` 里的 fan/photo/follow —— 实测存在的唯一字段。"""
    src = _impl_source()
    assert "ownerCount" in src, (
        "数字在 ownerCount 对象里（VisionUserProfile 上没有平铺的 fan 字段）"
    )
    for f in ("fan", "photo", "follow"):
        assert f in src, f"缺字段 {f}"


def test_does_not_query_nonexistent_fields():
    """⚠️ 这些字段**实测不存在**（猜错的代价：整条查询 400，什么都拿不到）。"""
    src = _impl_source()
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    code = re.sub(r"#.*", "", code)
    for bogus in ("likedCount", "photoCount", "fanCount", "followCount"):
        assert bogus not in code, f"{bogus} 在 GraphQL 上**不存在**"


def test_uses_page_context_for_credentials():
    """GraphQL 免签名，但**要 cookie** ⇒ 必须在页面上下文里发。"""
    src = _impl_source()
    assert "_JS_POST" in src, (
        "应在页面上下文里 fetch（credentials: include）；"
        "未登录会返回 result=2 / userProfile=null"
    )


# =============================================================================
# ⚠️⚠️ 两次线上事故的教训（2026-10-07）
# =============================================================================

def test_does_not_navigate_before_graphql():
    """GraphQL **不需要**先跳转页面（实测推翻我先前的假设）。

    我曾以为"GraphQL 在当前页面发 fetch ⇒ 会拿到当前页用户的数字"，
    于是先 `goto` 目标主页再查。**两处都错**：

      ① 跳转**经常失败**（实测 `打开 …/profile/3xep… 失败：Error`），
         失败还连带让同一会话里 `profile/feed` 的签名抓不到
         ⇒ **作品列表一起挂**
      ② **根本不需要跳** —— `visionProfile(userId:…)` 自带 userId 参数。

    实测证据（同一份日志里）：
        GraphQL 3xep6p7wbnqcvj6 → 粉丝=0 关注=8 作品=0
    「关注 8」是「沈阳」的真实值 ⇒ 请求确实命中了目标用户。
    """
    src = _impl_source()
    assert '_pages_for("__gql__"' not in src, (
        "不要为 GraphQL 跳转页面 —— 它自带 userId；"
        "且跳转失败会连带弄挂 profile/feed 的签名（2026-10-07 实测）"
    )
    assert "page.goto(" not in src, (
        "get_user_profile_impl 里不该再有页面跳转"
    )


def test_prefers_init_state_over_graphql():
    """★ 必须**优先** `window.INIT_STATE`（2026-10-07 实测精度差异）。

    同一用户（uid=3xep6p7wbnqcvj6）实测：

        GraphQL    {"fan":"1.3万", "photo":null, "follow":8}
        INIT_STATE {"fan":12551, "like":55163, "follow":8, "photo_public":176}
        页面显示   粉丝 1.3万 / 获赞 5.5万

    ⇒ GraphQL 给的是**四舍五入的展示字符串**（"1.3万"），
      反解成 13000 比真实 12551 **多 449**；
      且 GraphQL 上**没有获赞字段**。
    ⇒ INIT_STATE 才是精确值，且含获赞。

    ⚠️ 这个差别是本文件存在的根本理由（另一份独立调查报告提供的线索）。
    """
    src = _impl_source()
    assert "_read_profile_from_init_state" in src, (
        "必须优先用 INIT_STATE —— GraphQL 的数字被四舍五入，且没有获赞"
    )
    # INIT_STATE 分支在 GraphQL **调用**之前
    # ⚠️ 不能用 "visionProfile" 比较位置 —— 它在方法 docstring 里也出现过
    _call = "init = await self._read_profile_from_init_state(uid)"
    _gql = 'query = (\n                "query{ visionProfile'
    assert _call in src, "找不到 INIT_STATE 调用点"
    if _gql not in src:
        _gql = "ownerCount{ fan photo follow photo_public }"
    assert src.index(_call) < src.index(_gql), (
        "INIT_STATE 读取必须排在 GraphQL 之前（它的数字更准、还含获赞）"
    )
    # 取值字段要与实测一致
    assert 'oc.get("photo_public")' in src, "作品数在 photo_public（不是 photo）"
    assert 'oc.get("like")' in src, "获赞在 like（GraphQL 上没有，INIT_STATE 有）"


def test_init_state_validates_user_id():
    """INIT_STATE 也必须校验 `user_id`，避免拿到页面上别人的数据。"""
    src = inspect.getsource(
        __import__("app.services.platforms.kuaishou.client",
                   fromlist=["KuaishouClient"]).KuaishouClient
        ._read_profile_from_init_state
    )
    assert "user_id" in src, "缺少 user_id 校验"
    assert "INIT_STATE 的 user_id" in src, "身份不符时应记录并丢弃"


def test_does_not_use_profile_get():
    """**不再调用 `/rest/v/profile/get`** —— 它只能查自己。

    实测：请求目标 uid 时它返回的是**登录账号自己**
    （日志：`profile/get id 不符：请求 uid=3xep…，返回 ids=['2695872552']`）。
    """
    src = _impl_source()
    assert "PROFILE_GET" not in src, (
        "profile/get 只能查自己，不能用于查目标用户"
    )


def test_no_dual_id_check_left():
    """双 ID 校验已随之移除（`profile/get` 都不调了，没得可校验）。

    保留说明是因为它记录了两次踩坑：
      · 只比 `userId`（数字）⇒ 与请求的 `userDefineId` 永远不等
      · 放宽成"任一匹配"后，profile/get 返回的是自己 ⇒ 功能整体不可用
    ⇒ 结论是**别用这个接口**，而不是"把校验写对"。
    """
    src = _impl_source()
    assert "uid not in ids" not in src, (
        "profile/get 已不再使用，双 id 校验应随之移除"
    )


def test_returns_graphql_counts_as_fallback():
    """GraphQL 只作**兜底**，其数字是四舍五入值（"1.3万"）。"""
    src = _impl_source()
    assert "_parse_cn_count" in src, (
        "GraphQL 的 fan 是 '1.3万' 这类字符串，需要 _parse_cn_count"
    )
    # GraphQL 兜底里：作品数也要用 photo_public（实测 photo 返回 null）
    assert '"photo": _parse_cn_count(oc.get("photo_public"))' in src, (
        "GraphQL 兜底也要用 photo_public —— 实测 photo 返回 null"
    )
    assert "--- 兜底：GraphQL" in src, "GraphQL 应标注为兜底（INIT_STATE 才是首选）"


def test_videos_passes_uid_for_signature():
    """`profile/feed` 的签名**只在目标主页**发出 ⇒ `_post` 必须传 uid。

    ⚠️ 实测漏传的后果（就在同一天）：
        [kuaishou] 抓到签名但 /rest/v/profile/feed 不在其中
        （已有：…/profile/get, …/search/feed, …/search/user）
    ⇒ 作品列表 500。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient.get_user_videos)
    i = src.find("PROFILE_FEED,")
    assert i != -1, "没找到 profile/feed 调用"
    seg = src[i:i + 200]
    assert "uid=uid" in seg, (
        "profile/feed 调 _post 必须传 uid —— 签名只在目标用户主页发出"
    )


def test_signature_cache_key_matches_between_store_and_read():
    """**回归**：签名的「存」与「取」必须用同一个键（2026-10-07 线上 bug）。

    现象：日志上一行写着
        `[kuaishou] 抓到 2 个路径的签名：/rest/v/profile/feed, /rest/v/profile/get`
    紧接着却抛 `未能获取 /rest/v/profile/get 的接口签名`

    根因：我给 `cache_key` 加了 uid 后缀（`conn:uri:uid`），
    但**写入**用的是不带 uid 的 `f"{conn}:{path}"` ⇒ 存和取对不上。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._ensure_signed_url)
    assert 'cache_key = f"{conn}:{uri}"' in src, (
        "cache_key 必须是 conn:uri（不带 uid）—— 快手签名是**会话级**的"
    )
    assert 'f"{conn}:{path}"' in src, "写入缓存的键也不该带 uid"
    assert "_signed_urls.get(cache_key)" in src, "读取应统一用 cache_key"
