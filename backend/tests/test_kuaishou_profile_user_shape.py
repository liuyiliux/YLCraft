"""`profile/user` 的响应解析测试（2026-10-11，结构已由真实响应确认）。

## ⚠️ 关键：`ownerCount` 不在 `profile` 里面

真实响应（那份调查存的 `ks_profile_user.json`，原样）：

```json
{"result":1,"userProfile":{
    "profile":   {"user_name":"沈阳","headurl":"…","user_text":"…"},
    "ownerCount":{"fan":12548,"like":55165,"follow":8,"photo_public":176},
    "userDefineId":"1578058299","isFollowing":false,"gender":"M", …}}
```

⇒ **`ownerCount` 是 `profile` 的「兄弟节点」，挂在 `userProfile` 这一层**，
   不在 `profile` 里。

我原来的实现写成 `up["profile"].get("ownerCount")` ⇒ **永远取不到**，
线上日志表现为：

    profile/user[嵌套(profile)] … → 粉丝=None 关注=None 作品=None 获赞=None

⚠️ 我当时**误判成"响应有两种形状"**（嵌套/扁平），并写了分支去兼容 ——
   那是错的：真实原因就是**取错了层级**。这次回归到单一正确结构。

## 字段对照

| 含义 | 取值 |
|---|---|
| 昵称 | `userProfile.profile.user_name` |
| 头像 | `userProfile.profile.headurl` |
| 简介 | `userProfile.profile.user_text` |
| 粉丝 | `userProfile.ownerCount.fan` |
| 关注 | `userProfile.ownerCount.follow` |
| 作品 | `userProfile.ownerCount.photo_public` |
| **获赞** | `userProfile.ownerCount.like` ← GraphQL 没有这个 |
| 用户 id | `userProfile.userDefineId`（= URL 字符串 id） |
"""
from __future__ import annotations

import inspect
import re

REAL_RESPONSE = {
    "result": 1,
    "userProfile": {
        "profile": {
            "user_profile_bg_url": "//s2-10623.kwimgs.com/…svg",
            "user_id": "3xep6p7wbnqcvj6",
            "user_name": "沈阳",
            "headurl": "https://p2-pro.a.yximgs.com/uhead/…jpg",
            "user_text": "大家好～我叫沈阳没有小～\n但是也能给你带来快乐",
        },
        "ownerCount": {"fan": 12548, "like": 55165,
                       "follow": 8, "photo_public": 176},
        "isUserIsolated": False,
        "gender": "M",
        "userDefineId": "1578058299",
        "isFollowing": False,
        "showCollectTab": False,
        "livingInfo": {"living": False, "livingId": None, "iconType": 0},
    },
    "host-name": "public-bjmt-c26-kce-node311.idchb1az4.hb1.kwaidc.com",
}


def test_owner_count_is_sibling_of_profile():
    """★ `ownerCount` 在 `userProfile` 下，**不在** `profile` 里。"""
    up = REAL_RESPONSE["userProfile"]
    assert "ownerCount" in up, "ownerCount 应在 userProfile 这一层"
    assert "ownerCount" not in up["profile"], (
        "ownerCount 不在 profile 里 —— 从 profile 取会永远 None（我踩过这个坑）"
    )


def test_expected_field_values():
    """字段值与实测一致（精确值，非四舍五入）。"""
    up = REAL_RESPONSE["userProfile"]
    prof, oc = up["profile"], up["ownerCount"]
    assert prof["user_name"] == "沈阳"
    assert oc["fan"] == 12548
    assert oc["like"] == 55165        # 获赞 —— GraphQL 没有该字段
    assert oc["follow"] == 8
    assert oc["photo_public"] == 176
    assert up["userDefineId"] == "1578058299"


def test_helper_reads_owner_count_from_userprofile():
    """生产代码必须从 `userProfile` 取 `ownerCount`（不是从 profile）。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._post_profile_user)
    code = re.sub(r"#.*", "", src)
    code = re.sub(r'""".*?"""', "", code, flags=re.S)

    # 层级：userProfile → profile / ownerCount
    assert 'up = data.get("userProfile") or {}' in code
    assert 'prof = up.get("profile") or {}' in code
    assert 'oc = up.get("ownerCount") or {}' in code, (
        "必须从 userProfile 取 ownerCount —— 从 profile 取会永远 None"
    )
    # 取值字段
    for f in ('oc.get("fan")', 'oc.get("follow")',
              'oc.get("photo_public")', 'oc.get("like")'):
        assert f in code, f"缺字段 {f}"
    for f in ('prof.get("user_name")', 'prof.get("headurl")',
              'prof.get("user_text")'):
        assert f in code, f"缺身份字段 {f}"


def test_no_two_shape_branch():
    """⚠️ 不要再回到"两种形状"的兼容分支 —— 那是我误判出来的。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._post_profile_user)
    code = re.sub(r"#.*", "", src)
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert 'data.get("fans")' not in code, (
        "不应再有『扁平(profile/get)』那套取值 —— 单一结构即可"
    )
    assert "扁平(profile/get)" not in code


def test_validates_user_define_id():
    """必须用 `userDefineId`（= URL 字符串 id）校验，防冒充。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._post_profile_user)
    assert "userDefineId" in src
    assert "≠ 请求的" in src


def test_no_bili_helper():
    """⚠️ 不能用 B站客户端的方法（线上 500）。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient._post_profile_user)
    code = re.sub(r"#.*", "", src)
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert "_fix_bili_url" not in code, "代码里调用会 500"
    assert "_fix_bili_url" in src, "注释里应保留这个教训"
