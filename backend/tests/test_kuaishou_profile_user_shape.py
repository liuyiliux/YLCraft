"""`profile/user` 的**响应解析**测试（2026-10-11，两种形状都有实测依据）。

## 为什么有两种形状

线上日志（借 profile/get 签名调 profile/user）：

    profile/user（借 … 的签名）3xep… → 粉丝=None 关注=None 作品=None 获赞=None

⇒ 走了**扁平分支**：响应体**不是** `userProfile.profile.ownerCount` 嵌套，
  而是 profile/get 那种**顶层扁平**结构（`fans`/`follows`/`like`…）。

而那份独立调查存的 `ks_profile_user.json` 是**嵌套**结构：

    {"result":1,"userProfile":{"profile":{
        "user_name":"沈阳","headurl":"…",
        "ownerCount":{"fan":12548,"like":55165,
                      "follow":8,"photo_public":176}}}}

⇒ 两种都真实存在，解析器必须都认。
"""
from __future__ import annotations

import inspect
import re


def _shape(raw: dict) -> str:
    """复刻生产代码里的形状判定逻辑（用于断言，不重复实现解析）。"""
    nested = (raw.get("userProfile") or {}).get("profile")
    if isinstance(nested, dict) and (
        nested.get("ownerCount") or nested.get("user_name")
    ):
        return "嵌套(profile)"
    return "扁平(profile/get)"


def test_detects_nested_shape():
    """嵌套形状（那份调查的 ks_profile_user.json）。"""
    raw = {
        "result": 1,
        "userProfile": {"profile": {
            "user_name": "沈阳", "headurl": "https://x.jpg",
            "user_text": "…", "user_id": "3xep6p7wbnqcvj6",
            "ownerCount": {"fan": 12548, "like": 55165,
                           "follow": 8, "photo_public": 176},
        }},
    }
    assert _shape(raw) == "嵌套(profile)"


def test_detects_flat_shape():
    """扁平形状（线上日志里实际遇到的那个）。"""
    raw = {
        "result": 1,
        "userId": "2695872552", "userDefineId": "3xep6p7wbnqcvj6",
        "userName": "沈阳", "userHead": "https://x.jpg",
        "fans": 12548, "follows": 8, "like": 55165, "userTex": "…",
    }
    assert _shape(raw) == "扁平(profile/get)"


def test_empty_or_error_is_not_nested():
    """异常/空响应不能被误判成嵌套（否则会走到取不到值的分支）。"""
    for raw in ({}, {"result": 2}, {"result": 1, "userProfile": None}):
        assert _shape(raw) == "扁平(profile/get)", raw


def test_helper_handles_both_shapes():
    """生产代码里确实存在两套取值（不是只认一种）。"""
    import inspect

    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._post_profile_user)
    # 嵌套那套
    for f in ('oc.get("fan")', 'prof.get("user_name")', 'prof.get("headurl")'):
        assert f in src, f"嵌套分支缺 {f}"
    # 扁平那套
    for f in ('data.get("fans")', 'data.get("userName")',
              'data.get("userHead")', 'data.get("follows")'):
        assert f in src, f"扁平分支缺 {f}"
    # 形状标记（便于日志排查）
    assert "shape" in src, "应在日志里标注用的是哪种形状"


def test_no_bili_helper():
    """⚠️ 不能用 B站客户端的方法（线上 500）。

    日志：`'KuaishouClient' object has no attribute '_fix_bili_url'`
    """
    import inspect

    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._post_profile_user)
    # ⚠️ 只看**代码**：注释里必须能提到这个坑（那是教训），
    #   但代码里绝不能调用它 —— 否则线上 500。
    code = re.sub(r"#.*", "", src)
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert "_fix_bili_url" not in code, (
        "这是 B站客户端的方法，快手没有 —— 代码里调用会 500"
    )
    # 反过来：注释里**应该**留下这个教训，避免后人再踩
    assert "_fix_bili_url" in src, "注释里应保留这个坑的说明（防止再犯）"
