"""抖音"环境受限"必须报错而不是静默返回 0 条。

## 背景（2026-09-26 实测）

用户界面搜索抖音显示"找到 0 条结果"，让人以为是自己关键词的问题。
实测对照：

    用户真实 Chrome    → 搜索返回 5 条（正常）
    Patchright 自动化  → 搜索返回 0 条（data=[]，msg 为空）
                         但账号接口**正常**（user=True）

即抖音限制的是**自动化环境的搜索接口**，与 Cookie 有效性无关。

## 为什么必须抛错

空数组会被上层理解成"没搜到"。原来的代码在两层都把异常吞掉：
  1. `crawler/service.py::_search_via_platforms` 的 `except Exception: return []`
  2. `crawler/service.py::search_videos` 失败后降级到 yt-dlp（再失败一次）
最终用户只能看到"找到 0 条结果"，完全查不出原因。
"""

from __future__ import annotations

import inspect

import pytest


def test_platform_unavailable_error_exists():
    """要有专门的异常类型区分"平台不可用"与"搜索失败"。"""
    from app.services.platforms.douyin.client import PlatformUnavailableError

    assert issubclass(PlatformUnavailableError, RuntimeError)


def test_search_raises_when_cookie_ok_but_empty():
    """cookie 有效却搜不到 → 必须抛 PlatformUnavailableError。

    判据：搜索空 + 账号接口正常。这说明不是登录问题，
    而是搜索接口被限制，要如实告诉用户。
    """
    from app.services.platforms.douyin import client as dy_client

    src = inspect.getsource(dy_client.DouyinClient._raise_if_environment_degraded)
    assert "PlatformUnavailableError" in src
    assert "cookie_ok" in src or "uid" in src, "应区分 cookie 是否有效两种情况"
    assert "真实 Chrome" in src, "应给出实测对照作为依据"


def test_search_calls_degraded_probe_on_empty():
    """搜索返回空时必须调用探测，否则无法区分"没结果"与"被限制"。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "_raise_if_environment_degraded" in src


def test_probe_does_not_use_call_which_raises_on_status_8():
    """探测不能用 self._call()。

    实测：_call 见到 status_code != 0 就抛 RuntimeError，
    而抖音受限时恰恰返回 8 —— 会让探测自身变成异常被吞掉，
    于是永远不会报错（这正是修复前的状态）。
    """
    from app.services.platforms.douyin import client as dy_client

    src = inspect.getsource(dy_client.DouyinClient._raise_if_environment_degraded)
    assert "self._call(" not in src, "探测不能用 _call（它会对 status_code=8 抛错）"
    assert "_http_client" in src, "应直接发原始请求"


def test_crawler_does_not_swallow_platform_unavailable():
    """crawler 层不得把 PlatformUnavailableError 吞成空列表。"""
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    assert "PlatformUnavailableError" in src, "应单独 except 并重新抛出"

    src2 = inspect.getsource(crawler_service.CrawlerService.search_videos)
    assert "PlatformUnavailableError" in src2, "不应降级到 yt-dlp 再失败一次"


def test_module_imports_platform_unavailable_error():
    """crawler 必须真的 import 了这个异常（否则 except 永远不生效）。"""
    from app.services.crawler import service as crawler_service

    assert hasattr(crawler_service, "PlatformUnavailableError")


# =============================================================================
# 2026-10-11：`aweme/post` 被**稳定封禁**（不是概率波动）
# =============================================================================
#
# 用户报错：获取作品列表失败 …ArgusSecurityPlugin Uifid Not Found。
#
# 实测（连打 8 次，换 UA / 补 msToken / 加 a_bogus 签名 / 换 sec_uid）：
#
#     aweme/post     403 × 8/8      ← 一次都没过
#     aweme/detail   403
#     profile/self   200 ✅          ← 登录态是好的
#     profile/other  200 ✅
#
# ⇒ 这是**按路径的稳定封禁**，不是"概率 5/8"，"稍后重试"是**无效建议**。


def test_403_message_does_not_advise_retry():
    """**回归**：403 抛出的**文案**不能再说"概率性拦截／请稍后重试"。

    原文案会让用户（和 AI Agent）反复重试，而实测**重试永远无效**
    —— 8/8 全拦。错误提示**指向一个做不到的动作**比不提示更糟。

    ⚠️ 这里只看 `raise` 的那段（源文件里会引用旧说法来说明"它错在哪"，
       所以不能对整个函数做 `in` 判断 —— 第一版就这么写错了）。
    """
    from app.services.platforms.douyin import client as dy_client

    src = inspect.getsource(dy_client.DouyinClient._call)
    # 截取 raise 到结尾的部分 = 用户真正看到的文案
    idx = src.find("raise PlatformUnavailableError(")
    assert idx != -1, "没找到 403 的 raise 分支"
    msg = src[idx:]

    assert "请稍后重试" not in msg, (
        "403 文案不应再建议'稍后重试' —— 实测重试无效（8/8 全拦）"
    )
    # ⚠️ 不能简单断言 "概率" not in msg ——
    #    文案里"**不是**概率波动"是正确的（在**否定**旧说法）。
    #    这里查的是"把概率当原因"的旧表述。
    assert "概率性拦截" not in msg, "不该再把'概率性拦截'当成原因"
    assert "重试没有用" in msg or "稳定封禁" in msg, (
        "应如实说明这是稳定封禁、重试无用"
    )


def test_403_message_does_not_blame_login_state():
    """**回归**：403 文案不能说"检查登录态是否失效"。

    实测同一登录态下 `profile/self` / `profile/other` 都是 200 ——
    登录态是好的。把用户引去重新登录是**错误方向**，白花时间。
    """
    from app.services.platforms.douyin import client as dy_client

    src = inspect.getsource(dy_client.DouyinClient._call)
    idx = src.find("raise PlatformUnavailableError(")
    assert idx != -1
    msg = src[idx:]

    assert "检查登录态是否失效" not in msg, (
        "不该把'登录态失效'作为可能原因 —— 实测登录态正常"
    )
    assert "不是你的登录态失效" in msg or "不是**登录态" in msg or (
        "登录态" in msg and "正常返回 200" in msg
    ), "应明确排除'登录态问题'这个方向"


def test_documents_that_signature_does_not_help_post():
    """文档要记下：**a_bogus 签名救不了 aweme/post**（避免重复劳动）。

    `apis.py` 已记过"a_bogus 对**搜索**无用"；这里是**另一个端点**
    的另一次实验，结论同样是"签名救不了"。
    不记的话，下一个人会再去试一遍签名。
    """
    from app.services.platforms.douyin import client as dy_client

    # 说明可以写在 docstring 里（面向维护者），只要记下来即可
    doc = inspect.getdoc(dy_client.DouyinClient._call) or ""
    src = inspect.getsource(dy_client.DouyinClient._call)
    assert "a_bogus" in doc or "a_bogus" in src, (
        "应记录'加签名也无效'，避免重复实验"
    )


def test_users_videos_maps_risk_control_to_503():
    """**回归**：`/users/videos` 遇到风控要回 **503**，不是 500。

    500 = 我们的服务坏了；503 = 平台侧不可用。两者对用户的含义完全不同
    —— 抖音这个封禁不是我们的 bug，回 500 会让人以为程序故障。
    """
    from app.api.v1 import users

    src = inspect.getsource(users.get_user_videos)
    assert "RiskControlError" in src, "应单独 except 风控异常"
    assert "503" in src, "风控要映射成 503"


def test_users_videos_uses_type_not_string_matching():
    """用**异常类型**判断，不做字符串匹配。

    字符串匹配（`"403" in str(exc)`）在改文案时会**静默失效** ——
    这是该仓库明确记录过的教训（见 `PlatformUnavailableError` 的注释）。
    """
    from app.api.v1 import users

    src = inspect.getsource(users.get_user_videos)
    assert 'in str(exc)' not in src, "不要用字符串匹配判风控"
    assert '"403" in' not in src
