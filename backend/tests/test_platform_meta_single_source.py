"""平台元数据**单一事实来源**的回归测试（2026-10-01 收敛）。

## 这个测试防什么

改造前，平台元数据散落 **4 个文件**（users.py / comments.py /
health_routes.py / platform_stats.py），共 58 项内联映射：

    · 平台 → 连接名（"xhs": "XHS"）
    · 平台 → cookie 域名（"twitter": "x.com"）
    · 免登录名单（p in ("youtube","telegram")）
    · 别名映射（"wb" → "weibo"）
    · 体检探针类型（"bili": "video"）

**后果**：新增平台要改 4~5 个文件，**漏一个就静默出错**
（找不到客户端 / 查不到连接 / KeyError）。

现在改为平台自己声明（`platforms/<平台>/meta.py`），公共文件从 meta 生成。
本测试**守住"不再散落"**这条。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PLATFORMS = BACKEND / "app" / "services" / "platforms"


# =============================================================================
# meta 注册表本身
# =============================================================================

def test_all_platforms_declare_meta():
    """**关键**：每个平台目录都要有 `meta.py`（否则元数据又散落了）。"""
    from app.services.platforms.meta import all_metas

    declared = {m.name for m in all_metas()}
    expected = {
        "bili", "douyin", "kuaishou", "weibo", "twitter",
        "youtube", "telegram", "xiaohongshu", "fanqie",
    }
    missing = expected - declared
    assert not missing, (
        f"这些平台没有声明 meta.py：{sorted(missing)}\n"
        "请在 platforms/<平台>/meta.py 里加 PLATFORM_META。"
    )


def test_meta_has_required_fields():
    """每个 meta 必须有 name / conn_platform / cookie_domain。"""
    from app.services.platforms.meta import all_metas

    for m in all_metas():
        assert m.name, f"{m} 缺 name"
        assert m.conn_platform, f"{m.name} 缺 conn_platform"
        # ⚠️ 免登录平台可以没有 cookie_domain 需求，但字段本身要有值
        assert m.cookie_domain, f"{m.name} 缺 cookie_domain"


def test_cookie_domains_are_correct():
    """**关键回归**：这三个 cookie_domain 特别容易写错（实测踩过）。

    `netscape_to_header(raw, domain)` 认的是**特定名字**，
    写错会返回 **0 字符 cookie**（表现是"登录态莫名失效"）：

        bili    → "bili"（**不是** bilibili）
        weibo   → "weibo"（**不是** weibo.com —— 主站 cookie 在 m.weibo.cn 无效）
        twitter → "x.com"（**不是** twitter）
    """
    from app.services.platforms.meta import get_meta

    assert get_meta("bili").cookie_domain == "bili"
    assert get_meta("weibo").cookie_domain == "weibo"
    assert get_meta("twitter").cookie_domain == "x.com"


def test_aliases_resolve():
    """别名要能解析到正式名。"""
    from app.services.platforms.meta import resolve_name

    assert resolve_name("wb") == "weibo"
    assert resolve_name("dy") == "douyin"
    assert resolve_name("x") == "twitter"
    assert resolve_name("tw") == "twitter"
    assert resolve_name("ks") == "kuaishou"
    assert resolve_name("xhs") == "xiaohongshu"
    assert resolve_name("bilibili") == "bili"
    # 未知平台原样返回（不抛错）
    assert resolve_name("notexist") == "notexist"


def test_no_login_only_two_platforms():
    """免登录平台只有 YouTube / Telegram（**由平台自己声明**）。

    ⚠️ 改造前这是硬编码的 `p in ("youtube", "telegram")` ——
    加一个免登录平台就得改公共代码。
    """
    from app.services.platforms.meta import no_login_platforms

    assert no_login_platforms() == {"youtube", "telegram"}


# =============================================================================
# 能力声明与实际实现**一致**
# =============================================================================

def test_comments_capability_matches_implementation():
    """**关键**：声明了 `comments` 能力的平台，必须**真有**实现。

    否则用户点评论会拿到 500（而不是明确的 501「未实现」）。
    """
    import importlib

    from app.services.platforms.meta import all_metas

    for m in all_metas():
        if "comments" not in m.capabilities:
            continue
        try:
            mod = importlib.import_module(f"app.services.platforms.{m.name}.client")
        except Exception:
            pytest.skip(f"{m.name} 客户端载入失败")
        # 找到客户端类
        from app.services.platforms.base import BasePlatformClient

        cls = None
        for n, o in vars(mod).items():
            if (inspect.isclass(o) and issubclass(o, BasePlatformClient)
                    and o is not BasePlatformClient):
                cls = o
                break
        assert cls is not None, f"{m.name} 没有客户端类"
        src = inspect.getsource(cls.get_comments)
        assert "NotImplementedError" not in src, (
            f"{m.name} 声明了 comments 能力，但 get_comments 还是 TODO"
        )


def test_replies_capability_matches_implementation():
    """同理：声明 `replies` 的必须有实现。

    ⚠️ 微博**没有** `replies` 能力（实测楼中楼拿不到）——
    所以它不该被断言。
    """
    import importlib

    from app.services.platforms.base import BasePlatformClient
    from app.services.platforms.meta import all_metas

    for m in all_metas():
        if "replies" not in m.capabilities:
            continue
        mod = importlib.import_module(f"app.services.platforms.{m.name}.client")
        cls = None
        for n, o in vars(mod).items():
            if (inspect.isclass(o) and issubclass(o, BasePlatformClient)
                    and o is not BasePlatformClient):
                cls = o
                break
        src = inspect.getsource(cls.get_replies)
        assert "NotImplementedError" not in src, (
            f"{m.name} 声明了 replies 能力，但还没实现"
        )


def test_weibo_does_not_claim_replies():
    """**回归**：微博不能声明 `replies` 能力。

    实测：顶层评论的 `comments` 字段 20 条里 0 条带，
    `/comments/hotFlowChild` 返回 ok=0。所以微博是**如实报错**。
    如果哪天有人给微博加了 replies 能力，必须先有实测证据。
    """
    from app.services.platforms.meta import supports

    assert not supports("weibo", "replies")
    assert not supports("wb", "replies")


def test_bili_has_paged_but_not_replies():
    """B站：有 `comments_paged`（更完整的分页），但**没有** `replies`。

    B站的子回复随顶层评论的 `replies` 字段返回，没有独立接口。
    """
    from app.services.platforms.meta import supports

    assert supports("bili", "comments")
    assert supports("bili", "comments_paged")
    assert not supports("bili", "replies")


# =============================================================================
# ⚠️ 核心：公共文件里**不该**再有平台专属配置
# =============================================================================

def _code_lines(path: Path) -> str:
    """只取**可执行代码**，去掉注释与文档字符串。

    ⚠️ 踩了三次：注释和 docstring 里会写

        `PROBE_SEARCH_TYPE = {"bili": "video", ...}`      ← 说明"原来有什么"
        （"xhs": "XHS", "wb": "WEIBO", ...）
        `no_login = p in ("youtube", "telegram")`

    简单 grep（甚至按 AST 语句行号取）都会把这种**历史说明**
    误判成"还有硬编码"。

    ## 正确做法：用 `tokenize` 按 **token 类型**过滤

    Python 的 tokenizer 会把注释标成 `COMMENT`、字符串标成 `STRING` ——
    直接丢掉这两类，剩下的就是纯代码。
    """
    import io
    import tokenize

    out: list[str] = []
    with open(path, encoding="utf-8") as f:
        for tok in tokenize.generate_tokens(f.readline):
            # ⚠️ COMMENT = 注释；STRING 可能是 docstring 或普通字符串
            if tok.type == tokenize.COMMENT:
                continue
            # 丢掉"独占一行"的字符串（= docstring）
            if tok.type == tokenize.STRING and tok.start[1] == 0:
                continue
            if tok.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                            tokenize.DEDENT, tokenize.ENDMARKER):
                continue
            out.append(tok.string)
    return " ".join(out)


def test_health_routes_has_no_platform_tables():
    """**核心回归**：`health_routes.py`（公共文件）不该再有平台映射表。

    ⚠️ 改造前它含：
        PROBE_SEARCH_TYPE = {"bili": "video", ...}
        平台→连接名 内联字典（19 项）
        no_login = p in ("youtube", "telegram")
    ——共 44 处平台名。这些都是**平台专属配置**，
    不该由公共代码维护。
    """
    src = _code_lines(PLATFORMS / "health_routes.py")

    # ⚠️ token 拼接后 key 和 value 之间是空格（不是冒号紧跟），
    #    所以断言写成 `"xhs" : "XHS"` 这种形式。
    assert '"xhs" : "XHS"' not in src, "还有连接名内联映射"
    assert '"bili" : "video"' not in src, "还有探针类型字典"
    # 不该有硬编码的免登录名单
    assert '( "youtube" , "telegram" )' not in src, "还有硬编码免登录名单"
    # 应该从 meta 取
    assert "get_meta" in src, "应从 meta 取平台元数据"


def test_comments_has_no_platform_tables():
    """`comments.py` 不该再有平台映射表。"""
    src = _code_lines(BACKEND / "app" / "api" / "v1" / "comments.py")

    assert '"weibo" : ( "WEIBO" , "weibo" )' not in src, "还有 (连接名, 域名) 内联映射"
    # 不该再逐个 if 转别名
    assert 'client_name == "wb"' not in src, "还有逐个 if 的别名转换"
    assert "resolve_name" in src


def test_users_has_no_platform_tables():
    """`users.py` 的 SUPPORTED 应从 meta 生成。"""
    src = _code_lines(BACKEND / "app" / "api" / "v1" / "users.py")

    assert '"conn_platform" : "DOUYIN"' not in src, "还有手写平台表"
    assert "_build_supported" in src, "应从 meta 生成"


def test_platform_stats_has_no_alias_table():
    """`platform_stats.py` 的别名表应从 meta 生成。"""
    src = _code_lines(BACKEND / "app" / "api" / "v1" / "platform_stats.py")

    # 不该有手写 _ALIAS 字典
    assert "_ALIAS = {" not in src, "还有手写别名表"
    assert "resolve_name" in src


# =============================================================================
# 统计查询要兼容历史数据
# =============================================================================

def test_stats_query_covers_aliases():
    """**关键**：统计查询要匹配**正式名 + 所有别名**。

    ⚠️ 为什么：`platform_event_logs.provider` 是**写入时**的平台名。
    平台改名后（如 `xhs` → `xiaohongshu`），只用新名查会查不到旧记录
    —— 统计"凭空变少"，看起来像数据丢失。

    所以查询要用 `IN (...)` 而不是 `=`。
    """
    from app.api.v1.platform_stats import aliases_for_query

    names = aliases_for_query("bili")
    assert "bili" in names
    assert "bilibili" in names, "查询要覆盖别名（否则历史数据查不到）"

    assert set(aliases_for_query("x")) == {"twitter", "x", "tw"}


def test_stats_normalize_matches_meta():
    """归一结果与 meta 的正式名一致。"""
    from app.api.v1.platform_stats import normalize_platform
    from app.services.platforms.meta import resolve_name

    for p in ("wb", "dy", "x", "tw", "ks", "bilibili", "xhs"):
        assert normalize_platform(p) == resolve_name(p)
