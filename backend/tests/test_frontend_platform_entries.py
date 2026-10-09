"""前端入口完整性回归测试（2026-10-01 补 A 时加）。

## 为什么要测"前端入口"

本仓库反复踩同一个坑：**后端实现了，但前端下拉里没有** ——
用户根本选不到，功能等于不存在。已知犯过至少三次：

  · X（twitter）：`/users/*` 早实现，但「我的数据」下拉漏了
  · 快手：同样漏过
  · YouTube / Telegram / 微博：2026-10-01 又漏（本次修复）

这种"漏"**不报错**、测试也全绿 —— 只能靠**断言入口存在**来守住。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"{rel} 不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 博主中心
# =============================================================================

def test_platform_users_lists_all_supported_backends():
    """**回归**：「博主中心」的下拉要覆盖后端 `/users/*` 支持的所有平台。

    后端 `users.py::SUPPORTED` 支持的平台，前端都该能选到 ——
    否则就是"业务可用但 UI 无入口"。
    """
    from app.api.v1.users import SUPPORTED

    src = _read("pages/platform-users/index.tsx")
    i = src.find("const PLATFORMS")
    assert i != -1, "找不到 PLATFORMS 定义"
    seg = src[i:i + 1800]

    # 后端支持的代表性平台（用主名，别名不算）
    expect = {
        "douyin": "抖音",
        "xiaohongshu": "小红书",
        "kuaishou": "快手",
        "weibo": "微博",
        "youtube": "YouTube",
        "telegram": "Telegram",
        "bili": "B站",
    }
    for value, label in expect.items():
        assert f"'{value}'" in seg, (
            f"博主中心缺 {label}（{value}）—— 后端已支持，但用户选不到"
        )
    # 后端也确实支持这些（防两边漂移）
    for p in ("weibo", "youtube", "telegram", "kuaishou"):
        assert p in SUPPORTED, f"后端 SUPPORTED 缺 {p}"


def test_no_login_platforms_declared():
    """**回归**：免登录平台要有 `NO_LOGIN_PLATFORMS` 标记。

    否则前端会显示"未找到连接 —— 请先到账号中心获取登录态"，
    而这两个平台**根本不需要登录**（YouTube 走 yt-dlp、
    Telegram 走 t.me/s）。用户会被误导去白折腾一遍。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "NO_LOGIN_PLATFORMS" in src, "要有免登录平台的标记集合"
    i = src.find("NO_LOGIN_PLATFORMS = ")
    seg = src[i:i + 200]
    for p in ("youtube", "telegram"):
        assert f"'{p}'" in seg, f"{p} 是免登录平台，要标进 NO_LOGIN_PLATFORMS"


def test_no_login_branch_shows_positive_message():
    """免登录平台在"没有连接"时应显示**正向提示**，不是警告。"""
    src = _read("pages/platform-users/index.tsx")
    # ⚠️ `NO_LOGIN_PLATFORMS.has(platform)` 在文件里出现**两次**：
    #   ① 深链判断  ② 渲染提示。要定位到**渲染**那处（含"无需登录"文案的）。
    idx = src.find("无需登录")
    assert idx != -1, "免登录平台应明确告诉用户'无需登录'"
    seg = src[max(0, idx - 600):idx + 200]
    assert "NO_LOGIN_PLATFORMS.has(platform)" in seg, (
        "渲染分支要按 NO_LOGIN_PLATFORMS 判断（不是按平台名硬编码）"
    )


def test_kuaishou_calls_profile_api_but_degrades_gracefully():
    """**2026-10-07 反转**：快手**应该**调 profile 接口了。

    ⚠️ 这条测试原来叫 `test_kuaishou_does_not_call_profile_api`，
    断言"快手分支**不该**调 getPlatformUserProfile"。那个结论基于
    2026-10-01 的判断"快手没有按 id 查资料的接口"——**已被抓包推翻**：

        `profile/get` 的 userId 在**页面 URL** 上（`/profile/{uid}`），
        不是 body/query。之前"传 userId 无效"是位置搞错了。

    ⇒ 现在要调，但必须**优雅降级**：
      1. 先用搜索结果渲染（昵称/头像立刻可见，不白屏）
      2. 再异步补统计；失败**不弹错误**，沿用搜索结果
         （未登录时后端返回 109→401，属预期，不该当成故障刷屏）
      3. 合并而非替换，别把搜索结果里已有的字段弄丢
    """
    src = _read("pages/platform-users/index.tsx")
    i = src.find("loadUserDetail = useCallback")
    assert i != -1
    seg = src[i:i + 2200]
    assert "'kuaishou'" in seg, "loadUserDetail 里要有 kuaishou 分支"
    ks_i = seg.find("'kuaishou'")
    next_branch = seg.find("} else {", ks_i)
    branch = seg[ks_i:next_branch if next_branch > ks_i else len(seg)]

    assert "getPlatformUserProfile" in branch, (
        "快手分支现在应该调 profile 接口补统计（抓包已证明可行）"
    )
    # 优雅降级：先用搜索结果渲染，失败不打断
    assert "setProfile(user)" in branch, "应先用搜索结果渲染，不白屏"
    assert "catch" in branch, "补统计失败要有 catch，不能让整个详情失败"
    # 合并而非替换
    assert "..." in branch, "应用 {...prev, ...res.data} 合并，别丢掉搜索结果的字段"


def test_kuaishou_backend_profile_can_query_others():
    """**2026-10-07 反转**：快手 `get_user_profile` **能**查别人了。

    ⚠️ 这条测试原来断言"抛 NotImplementedError"（依据是 2026-10-01 的
    结论"快手没有按 id 查博主资料的接口"）。那个结论**已被抓包推翻**：

        GET /rest/v/profile/get?__NS_hxfalcon=…
        · **请求体是空的** —— userId 不在 body 也不在 query
        · userId 在**页面 URL**（`kuaishou.com/profile/{uid}`）上
        · 之前"传 userId 无效"是因为**位置搞错了**

    所以现在断言：真正实现在 `_get_user_profile_impl`，且
    **必须带 uid 去做签名抓取**（签名是在目标用户主页上抓的）。
    """
    from app.services.platforms.kuaishou.client import KuaishouClient
    import inspect

    src = inspect.getsource(KuaishouClient.get_user_profile)
    assert "NotImplementedError" not in src, (
        "还在抛 NotImplementedError —— 2026-10-07 抓包已证明可以查别人"
    )

    impl = inspect.getsource(KuaishouClient._get_user_profile_impl)
    assert "uid=uid" in impl, "必须把目标 uid 传下去（签名在目标主页抓）"
    # !! 2026-10-07 线上事故：搜该用户显示的是**我自己账号**的数据（粉丝15 关注26）
    #   名字和数字全是自己的。原因是校验只 logger.warning 然后照常返回；
    #   且 GraphQL 是在**当前页面**（可能正是自己主页）发的。
    # => 现在必须**硬拒绝**。
    assert "uid not in ids" in impl, "必须两个 id 任一匹配（快手有 userId 数字 + userDefineId 字符串）"
    _i = impl.index("uid not in ids:")
    assert "return None" in impl[_i:_i + 400], (
        "身份对不上必须 return None —— 只记警告会拿自己的资料冒充别人"
    )


def test_kuaishou_pages_for_uses_target_uid():
    """`_pages_for` 传了 uid 就必须去**那个人的**主页。"""
    from app.services.platforms.kuaishou.client import KuaishouClient
    import inspect

    src = inspect.getsource(KuaishouClient._pages_for)
    assert "uid" in inspect.signature(KuaishouClient._pages_for).parameters
    assert "/profile/{uid}" in src, "没有用目标 uid 拼主页 URL"


# =============================================================================
# 「我的数据」页：免登录平台**不该**出现在这里
# =============================================================================

def test_my_platform_data_excludes_loginless_platforms():
    """「我的数据」是查**自己**的账号 —— 免登录平台没有这个概念。

    ⚠️ 这条是**反向断言**：YouTube/Telegram **不该**被加进去。
    它们免登录、没有"我的账号"，加进去只会让用户困惑
    （选了却永远拿不到数据）。
    """
    src = _read("pages/my-platform-data/index.tsx")
    i = src.find("const PLATFORMS")
    assert i != -1
    seg = src[i:i + 1500]
    for p in ("youtube", "telegram"):
        assert f"'{p}'" not in seg, (
            f"{p} 是免登录平台，不该出现在「我的数据」（那里是查自己的账号）"
        )


# =============================================================================
# 后端 users.py
# =============================================================================

def test_users_py_has_telegram_and_youtube_as_no_login():
    """后端 `SUPPORTED` 里 youtube/telegram 要标 `no_login`。"""
    from app.api.v1.users import SUPPORTED

    for p in ("youtube", "telegram"):
        cfg = SUPPORTED.get(p)
        assert cfg is not None, f"SUPPORTED 缺 {p}"
        assert cfg.get("no_login"), f"{p} 应标记 no_login（它不需要连接）"


def test_client_alias_is_module_level():
    """**回归**：平台别名映射要提成模块级常量。

    原来散在 `_client_for` 里的 if-else —— 加了免登录分支后
    **两处都要用**，散着写必然漏一处（本仓库"同一映射写两遍会漂移"的教训）。
    """
    from app.api.v1 import users

    assert hasattr(users, "_CLIENT_ALIAS"), "别名映射要提成模块级"
    alias = users._CLIENT_ALIAS
    for k, v in (("xhs", "xiaohongshu"), ("wb", "weibo"), ("ks", "kuaishou")):
        assert alias.get(k) == v, f"别名 {k} → {v} 不对"
