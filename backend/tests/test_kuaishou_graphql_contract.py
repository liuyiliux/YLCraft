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
