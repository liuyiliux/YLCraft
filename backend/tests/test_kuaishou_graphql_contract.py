"""快手 GraphQL 取博主统计的**契约**测试（不联网、不需要浏览器）。

## 实测确认的事实（2026-10-07）

参考开源项目 MediaCrawler 的
`media_platform/kuaishou/graphql/vision_profile.graphql`，实测快手博主资料走
**GraphQL**（不是 REST）：

    POST https://www.kuaishou.com/graphql
    {
      "query": "query{ visionProfile(userId:\"<uid>\"){ result "
               "userProfile{ ownerCount{ fan photo follow } } } }"
    }

字段全部靠 GraphQL 的 `Did you mean` 报错试出来（introspection 被禁）：

| 试的东西          | 结果                                              |
|-------------------|---------------------------------------------------|
| `visionProfileUser` | 不存在。报错列出真实字段：visionProfile / visionProfileUserList / visionProfileReduced / visionMovieFeed / visionSearchUser |
| 参数 `id` / `user_id` | 不认，只认 **`userId`**                     |
| `userProfile{ fan }`  | ✗ 字段不存在 → `Did you mean "ownerCount"?`      |
| `userProfile{ photoCount }` | ✗ → `Did you mean "ownerCount"?`           |
| `ownerCount{ fan }`  | ✓ **存在**                                        |
| `ownerCount{ photo }` | ✓ **存在**                                        |
| `ownerCount{ follow }`| ✓ **存在**                                        |
| `ownerCount{ like }`  | ✗ 不存在                                          |
| `ownerCount{ video/note/total/public }` | ✗ 都不存在            |

⚠️ **没有「获赞」字段** —— 页面上那个「获赞 5.5万」不在这条通道里。
我先前猜的 `likedCount` / `photoCount` / `fanCount` 全部不存在。

未登录时实测返回 `{"result":2,"userProfile":null}` ⇒ 需要登录态的浏览器上下文。

## 这些测试的作用

防止再有人（包括我）按 REST 的直觉去猜 `fans`/`follows`/`likedCount`
—— 那些字段**在 GraphQL 里一个都不存在**，只能靠上面的表。
"""
from __future__ import annotations

import inspect
import re


def _impl_source() -> str:
    from app.services.platforms.kuaishou.client import KuaishouClient

    return inspect.getsource(KuaishouClient._get_user_profile_impl)


def test_uses_graphql_endpoint():
    """必须打 `/graphql`，不是 REST 的 `/rest/v/profile/get`。"""
    src = _impl_source()
    assert "/graphql" in src, "没走 GraphQL 端点"
    assert "visionProfile" in src, "没调用 visionProfile 查询"


def test_queries_owner_count_fields():
    """必须查 `ownerCount` 里的 fan/photo/follow —— 这三个是实测存在的唯一字段。"""
    src = _impl_source()
    assert "ownerCount" in src, (
        "数字在 ownerCount 对象里（VisionUserProfile 上没有平铺的 fan 字段）"
    )
    for f in ("fan", "photo", "follow"):
        assert f in src, f"缺字段 {f}"


def test_does_not_query_nonexistent_fields():
    """⚠️ 这些字段**实测不存在**，别再猜了。

    （猜错的代价：整条查询返回 400，什么都拿不到。）
    """
    src = _impl_source()
    # 只允许出现在注释里的字段名
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    code = re.sub(r"#.*", "", code)
    for bogus in ("likedCount", "photoCount", "fanCount", "followCount"):
        assert bogus not in code, (
            f"{bogus} 在 GraphQL 的 VisionUserProfileOwnerCount 上**不存在**"
        )


def test_uses_page_context_for_credentials():
    """GraphQL 免签名，但**要 cookie** ⇒ 必须在页面上下文里发。"""
    src = _impl_source()
    assert "_JS_POST" in src, (
        "应在页面上下文里 fetch（credentials: include），"
        "未登录会返回 result=2 / userProfile=null"
    )


def test_signature_cache_key_matches_between_store_and_read():
    """**回归**：签名的「存」与「取」必须用同一个键（2026-10-07 线上 bug）。

    现象：日志上一行写着
        `[kuaishou] 抓到 2 个路径的签名：/rest/v/profile/feed, /rest/v/profile/get`
    紧接着却抛
        `未能获取 /rest/v/profile/get 的接口签名`

    根因：我上一版给 `cache_key` 加了 uid 后缀（`conn:uri:uid`），
    但**写入**用的是不带 uid 的 `f"{conn}:{path}"` ⇒ 存和取对不上。

    这类 bug 只在**真跑**时暴露（单测不碰缓存），所以这里钉死键的形状。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._ensure_signed_url)
    assert 'cache_key = f"{conn}:{uri}"' in src, (
        "cache_key 必须是 conn:uri（不带 uid）—— 快手签名是**会话级**的"
    )
    assert 'f"{conn}:{path}"' in src, "写入缓存的键也不该带 uid"
    assert "_signed_urls.get(cache_key)" in src, "读取应统一用 cache_key"


# =============================================================================
# ⚠️⚠️ 最重要的一条：**绝不拿自己的资料冒充别人**（2026-10-07 线上事故）
# =============================================================================

def test_navigates_to_target_profile_before_graphql():
    """GraphQL 必须在**目标用户主页**的上下文里发。

    ⚠️ 事故经过：搜「沈阳」点查看，界面显示的是
       **逸流AI（我自己）粉丝15 关注26 获赞318**。

    原因：GraphQL 是用 `_JS_POST` 在**当前页面**发 fetch 的，
    而当前页面可能是**自己的主页** ⇒ 拿回的是自己的 `ownerCount`。
    ⇒ 发查询前必须先 `goto` 目标主页。
    """
    src = _impl_source()
    assert '_pages_for("__gql__", uid)' in src, (
        "GraphQL 前必须先打开目标用户主页（否则拿到的是自己的数字）"
    )
    assert "page.goto(page_url" in src, "要真的导航，不只是算个 URL"


    """**硬校验**：`profile/get` 返回的用户必须等于请求的用户。

    事故里原来的校验只 logger.warning 然后照常返回 —— 名字和数字是
    「自己」的、id 又填回「目标」，成了张冠李戴。

    => 身份对不上必须 return None。

    ## 但要认**两个** id（2026-10-07 第二次踩坑）

    快手同时有 userId（数字，如 1578058299）和
    userDefineId（字符串，即我们请求的 3xep6p7wbnqcvj6）。
    只拿 userId 去比 uid **必然不等** => 硬校验一直触发，
    功能整个用不了（success=False「用户不存在或资料不可见」）。
    """
    src = _impl_source()
    assert 'payload.get("userId")' in src, "没取 userId（数字 id）"
    assert 'payload.get("userDefineId")' in src, "没取 userDefineId（字符串 id）"
    assert "uid not in ids" in src, (
        "必须「两个 id 任一匹配」—— 只比 userId 会与 userDefineId 永远不等"
    )
    i = src.index("uid not in ids:")
    assert "return None" in src[i:i + 400], (
        "身份对不上必须 return None —— 只记警告会拿自己的资料冒充别人"
    )
    assert "if got_uid != uid:" not in src, (
        "残留单字段比较（只比 userId）会永远误判 —— 2026-10-07 线上事故"
    )

def test_graphql_result_validated_against_target():
    """GraphQL 的数字也要校验返回的用户是不是目标用户。"""
    src = _impl_source()
    assert "back_id" in src, "GraphQL 结果缺少身份校验"
    assert "丢弃数字" in src, "身份不符时必须丢弃 GraphQL 数字"
