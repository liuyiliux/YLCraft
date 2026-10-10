"""快手取博主资料的**契约**测试（不联网）。

## 结论来源（2026-10-10，两次实测 + 一份独立调查报告）

真正可用的资料接口是 **`POST /rest/v/profile/user`**：

    POST https://www.kuaishou.com/rest/v/profile/user?__NS_hxfalcon=<签名>&caver=2
    body: {"user_id": "<URL 里的字符串 id>"}
    → {"result":1,"userProfile":{"profile":{
         "user_name":"沈阳", "headurl":"…", "user_text":"…",
         "ownerCount":{"fan":12548,"like":55165,
                        "follow":8,"photo_public":176},
         "userDefineId":"1578058299", "user_id":"3xep6p7wbnqcvj6"}}}

原始响应见 `F:\workspace\简单脚本\ks_profile_user.json`。

## 三条「未登录能不能」（独立实测，唯一变量 = cookie）

| 数据 | 未登录 | 依据 |
|---|---|---|
| 博主资料 `profile/user` | ✅ 可以 | include→`result:1`；omit→`result:2` |
| 搜人 `search/user` | ❌ 不行 | include→`result:1`+30 用户；omit→`result:2` |
| 作品列表 `profile/feed` | ❌ 不行 | 页面自身请求就是 109 |

## 被证伪的两条路（别再走回头路）

1. **`/rest/v/profile/get`** —— 未登录恒 `{"result":109}`，死路。
   我曾拿它取"目标用户资料"，拿回的永远是登录账号自己。
2. **`window.INIT_STATE`** —— 那些数据是**搜索页缓存残留**：
   SSR HTML 里 8 个关键词全 0 命中；全量抓包里该页从未发出资料请求；
   数值还会漂移（12551→12548、55163→55165）。
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

def test_uses_profile_user_endpoint():
    """★ 必须用 `POST /rest/v/profile/user`。"""
    src = _impl_source()
    assert "PROFILE_USER" in src, (
        "必须用 /rest/v/profile/user —— profile/get 未登录恒 109（死路）"
    )


def test_does_not_read_init_state():
    """⚠️ `INIT_STATE` 是**搜索页缓存残留**，不是该页数据（独立实测证伪）。"""
    src = _impl_source()
    assert "_read_profile_from_init_state" not in src, (
        "INIT_STATE 已被证伪：SSR HTML 里 8 个关键词全 0 命中，"
        "全量抓包里该页从未发出资料请求，且数值会漂移"
    )


def test_does_not_use_profile_get():
    """`profile/get` 未登录恒 109，取不到任何东西。"""
    src = _impl_source()
    assert "_post(PROFILE_GET" not in src, (
        "profile/get 是死路（未登录恒 109），且它返回的是登录账号自己"
    )


def test_profile_user_ranked_before_graphql():
    """`profile/user` 应排在 GraphQL 兜底**之前**（数字精确、且含获赞）。

    ⚠️ 比较的是**调用点**，不是常量名 —— `PROFILE_USER` 在方法 docstring 里
    也出现过（那是解释为什么不用 profile/get 的注释），用 `index` 会误判。
    """
    src = _impl_source()
    call = "payload = await self._post("
    i_user = src.index(call)          # profile/user 的调用
    i_gql = src.index("--- 兜底：GraphQL")
    assert i_user < i_gql, (
        "profile/user 必须优先于 GraphQL 兜底（它数字精确且含获赞）"
    )


def test_field_names_match_measurement():
    """字段名与实测响应一致（`photo` 是 null，作品数在 `photo_public`）。"""
    src = _impl_source()
    assert 'oc.get("photo_public")' in src, "作品数在 photo_public（不是 photo）"
    assert 'oc.get("like")' in src, "获赞在 like"
    assert 'oc.get("fan")' in src, "粉丝在 fan"
    assert 'oc.get("follow")' in src, "关注在 follow"


def test_profile_user_body_uses_string_id_only():
    """body 只吃**URL 里的字符串 id**。

    实测：传"快手号"（1578058299）→ `{"result":21 参数格式错误}`。
    """
    from app.services.platforms.kuaishou.apis import build_profile_user_body

    assert build_profile_user_body("3xep6p7wbnqcvj6") == {
        "user_id": "3xep6p7wbnqcvj6",
    }
    assert build_profile_user_body("") == {"user_id": ""}


def test_profile_user_validates_user_id():
    """必须校验 `user_id` 是目标用户，避免拿到别人的数据。"""
    src = _impl_source()
    assert "profile/user 返回 %s ≠ 请求的 %s" in src, "缺少 user_id 校验"


# =============================================================================
# 签名 / GraphQL 兜底
# =============================================================================

def test_not_headless():
    """★ **快手对无头浏览器返回空白页** ⇒ 必须有头（2026-10-10 根因实测）。

    对照实验（同一 URL、同一流程，唯一变量是有无头）：

        无头：cookie=[]   页面正文 63 字符、标题为空   带签名请求 **0 个**
        有头：cookie=6 个  页面正文 1037 字符         带签名请求 **3 个**

    ⇒ 无头下快手返回 HTTP 200 但 **JS 根本不跑**，一个请求都不发
      （连不带签名的都没有）⇒ 签名**必然**抓不到。

    ⚠️ 这与登录态、与用哪个 URL **都无关**。此前我先后猜过
      "未登录不发""风控""cookie 过期"——**全部错误**。
    ⇒ 抓不到签名时**先查无头这个变量**，别再猜。
    """
    import inspect

    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._get_session)
    code = re.sub(r"#.*", "", src)          # 去掉注释，只看代码
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert "headless=True" not in code, (
        "不能写死 headless=True —— 实测快手对无头浏览器返回**空白页**"
        "（正文 63 字符、零请求），签名必定抓不到"
    )
    assert "YLCRAFT_KS_HEADLESS" in src, (
        "应通过环境变量控制，且默认有头（恢复无头需显式设 YLCRAFT_KS_HEADLESS=1）"
    )


def test_uses_graphql_as_fallback():
    """GraphQL 只作兜底，其数字是**四舍五入**的（`"1.3万"`）。"""
    src = _impl_source()
    assert "visionProfile" in src, "应保留 GraphQL 兜底"
    assert "_parse_cn_count" in src, 'GraphQL 的 fan 是 "1.3万" 这类字符串'
    assert '"photo": _parse_cn_count(oc.get("photo_public"))' in src, (
        "GraphQL 兜底也要用 photo_public —— 实测 photo 返回 null"
    )


def test_does_not_query_nonexistent_graphql_fields():
    """⚠️ 这些 GraphQL 字段**实测不存在**（猜错的代价：整条查询 400）。"""
    src = _impl_source()
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    code = re.sub(r"#.*", "", code)
    for bogus in ("likedCount", "photoCount", "fanCount", "followCount"):
        assert bogus not in code, f"{bogus} 在 GraphQL 上**不存在**"


def test_does_not_navigate_before_graphql():
    """GraphQL **不需要**先跳转页面（实测推翻我先前的假设）。

    跳转经常失败，且失败会连带让 `profile/feed` 的签名抓不到
    ⇒ 作品列表一起挂。
    """
    src = _impl_source()
    assert '_pages_for("__gql__"' not in src, (
        "不要为 GraphQL 跳转页面 —— 它自带 userId，且失败会连带弄挂 feed 签名"
    )


def test_uses_page_context_for_credentials():
    """GraphQL 免签名但要 cookie ⇒ 在页面上下文里发。"""
    src = _impl_source()
    assert "_JS_POST" in src


def test_videos_passes_uid_for_signature():
    """`profile/feed` 的签名**只在目标主页**发出 ⇒ `_post` 必须传 uid。

    ⚠️ 实测漏传的后果：
        [kuaishou] 抓到签名但 /rest/v/profile/feed 不在其中
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient.get_user_videos)
    i = src.find("PROFILE_FEED,")
    assert i != -1, "没找到 profile/feed 调用"
    assert "uid=uid" in src[i:i + 200], (
        "profile/feed 调 _post 必须传 uid —— 签名只在目标用户主页发出"
    )


def test_signature_cache_key_matches_between_store_and_read():
    """**回归**：签名的「存」与「取」必须同键（2026-10-07 线上 bug）。

    现象：日志刚打印"抓到 2 个路径的签名"，下一行就抛"未能获取…的签名"。
    根因：`cache_key` 加了 uid 后缀，但**写入**用不带 uid 的键。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._ensure_signed_url)
    assert 'cache_key = f"{conn}:{uri}"' in src, (
        "cache_key 必须是 conn:uri（不带 uid）—— 快手签名是**会话级**的"
    )
    assert 'f"{conn}:{path}"' in src, "写入缓存的键也不该带 uid"
    assert "_signed_urls.get(cache_key)" in src, "读取应统一用 cache_key"
