"""分页「谎报没有更多」的回归测试（2026-10-03）。

## 背景：抖音症状

用户选"每页 10 条"，页面只显示 9 条且**没有下一页**。但实测抖音单次
能返回 18 条，且服务端 `has_more=1`。两个 bug 叠加：

### Bug A：`page_size = min(want, 20)` 让"每页设置"变成"截断"
    每页 10 条  ->  发 count=10  -> 抖音只给 9 条（它手里有 18）
    每页 20 条  ->  发 count=20  -> 抖音给 17 条
    每页 50 条  ->  仍 count=20  -> 17 条
于是"每页条数"这个设置**只起截断作用，起不到分页作用**。

### Bug B：`_has_more` 取自**最后一次**响应
    首页  -> has_more=1, cursor=20  （抖音说"还有更多"）
    第2次 -> data=[]               （我们对 offset>0 拿不到）
    -> 用第2次的 has_more=0 覆盖 -> 前端显示"没有下一页"
**用失败的请求推翻了成功的请求。**

## 背景：微博症状（同型）

`_has_more` 被**写死 False**，理由记的是 2026-09-29 的实测
（"page=2 返回 173 字节错误页，since_id 为 None"）。但 2026-10-03 实测：

    page=1 10 条 / page=2 10 条 / page=3 10 条，page1 ∩ page2 = **0**

**微博能真翻页**，注释里"平台没有第 2 页"是**当时的**结论，没复验就
被当成永久事实写进了代码。抖音同样从"能翻"（09-27）变成"只有第一页"（09-28）。

## 这些断言锁住两件事
  1. `count` 必须给**平台分页粒度**，不能给用户选的显示条数
  2. `has_more` 不能被后续失败请求覆盖
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

DOUYIN = Path(__file__).resolve().parents[1] / "app" / "services" / "platforms" / "douyin" / "client.py"
WEIBO = Path(__file__).resolve().parents[1] / "app" / "services" / "platforms" / "weibo" / "search_patchright.py"


def _src(p: Path) -> str:
    if not p.exists():
        pytest.skip(f"{p.name} not found")
    return p.read_text(encoding="utf-8", errors="ignore")


def _search_body(p: Path, func: str) -> str:
    """抽出指定函数的源码文本。

    ⚠️ 不能靠"遇到缩进回退就结束"（第一版就是这么写的，实测失败）：
    多行函数签名里 `page: int = 1,` 的缩进比 `def` 浅一格，
    于是函数体被截成只剩签名 —— 断言必然失败（且失败原因具有误导性）。
    改为：从 `def` 行起，跳过括号未闭合的签名，再吃函数体。
    """
    lines = _src(p).splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"async def {func}(") or ln.strip().startswith(f"def {func}("):
            start = i
            break
    assert start is not None, f"{p.name} 找不到 {func}"

    # 1) 先找函数体真正开始的行（签名结束）
    depth = 0
    body_start = start
    for i in range(start, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth <= 0:
            body_start = i + 1
            break

    # 2) 从 body_start 吃到缩进回退
    indent = len(lines[body_start]) - len(lines[body_start].lstrip())
    out = lines[start:body_start]
    for ln in lines[body_start:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) < indent:
            break
        out.append(ln)
    return "\n".join(out)


def _strip_comments(text: str) -> str:
    """去掉注释 —— 否则断言会命中我写的说明文字。

    （这个坑本仓库踩过多次：`test_mobile_layout` 里
    「原来 return None」这种注释文本让断言失真。）
    """
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            continue
        # 去掉行尾注释：不在引号内的 #
        in_s, in_d = False, False
        cut = len(ln)
        for i, ch in enumerate(ln):
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            elif ch == "#" and not in_s and not in_d:
                cut = i
                break
        out.append(ln[:cut])
    return "\n".join(out)


# =============================================================================
# Bug A：count 必须给平台分页粒度
# =============================================================================

def test_douyin_page_size_not_limited_by_user_want():
    """抖音 page_size 不能是 min(want, 20)。

    ⚠️ 断言必须锚定**真实赋值语句**（`_strip_comments` 之后仍存在的那行），
    只判 `"page_size = min(want, SINGLE_PAGE_MAX)" in body` 是不够的：
    第一版就栽在这 —— 我只把新注释写在旧代码**上面**、没改赋值，
    而断言恰好去匹配注释里的文本，于是**测试通过但 bug 还在**。
    所以这里额外要求 `SINGLE_PAGE_MAX` 那一行存在，
    且 `min(want,` 后面必须不再跟 SINGLE_PAGE_MAX。
    """
    body = _strip_comments(_search_body(DOUYIN, "search"))
    assigns = [ln.strip() for ln in body.splitlines()
               if ln.strip().startswith("page_size")]
    assert assigns, "找不到 page_size 赋值"
    for a in assigns:
        assert "min(want," not in a, (
            f"page_size 仍被用户的『每页条数』限制（{a}）—— "
            f"选 10 条就只向抖音要 10 条，每页设置只剩截断作用"
        )
    assert any(a == "page_size = SINGLE_PAGE_MAX" for a in assigns), (
        f"page_size 应恒为 SINGLE_PAGE_MAX(20)，实际是：{assigns}"
    )


def test_douyin_single_page_max_is_20():
    """前提：抖音单页上限确实是 20（若平台改了，这里要跟着改）。"""
    from app.services.platforms.douyin.apis import SINGLE_PAGE_MAX
    assert SINGLE_PAGE_MAX == 20, (
        f"SINGLE_PAGE_MAX 变成了 {SINGLE_PAGE_MAX} —— "
        f"实测（2026-10-03）抖音 count 上限仍是 20，改了要重新验证"
    )


# =============================================================================
# Bug B：has_more 不能被后续失败请求覆盖
# =============================================================================

def test_douyin_has_more_from_first_response():
    """`_has_more` 必须来自首次成功响应，不能用循环最后一次的 data。"""
    body = _strip_comments(_search_body(DOUYIN, "search"))
    assert "first_has_more" in body, (
        "没有记录首次响应的 has_more —— "
        "翻页请求返回空时会覆盖首页的真实判断"
    )
    # ⚠️ 断言必须落在**真实赋值**上，不能只判字符串存在。
    # 变异测试发现：把 `server_has_more` 改回读 `data.get("has_more")`（即
    # 读循环最后一次响应）时，`first_has_more` 这个变量**仍然存在**，
    # 所以"存在性断言"放过了这个 bug —— 它只是被赋了个错值。
    # 这里要求 `_has_more` 真正**用到**首次响应的值。
    assert re.search(r"server_has_more\s*=\s*bool\(\s*first_has_more\s*\)", body), (
        "server_has_more 必须取自 first_has_more（首次成功响应）"
    )
    assert not re.search(r"server_has_more\s*=\s*bool\(\s*data\.get\(", body), (
        "server_has_more 又读回循环最后一次响应了 —— "
        "翻页请求返回空时会覆盖首页的真实判断（这正是要修的 bug）"
    )
    assert "reachable_more" in body, (
        "应把『服务端说有更多』与『我们能翻到』区分开，"
        "否则会给出一个点了就报错的下一页按钮"
    )


def test_douyin_reports_real_total():
    """抖音应回传真实可达条数（单次上限），让前端显示『共 N 条』。"""
    body = _strip_comments(_search_body(DOUYIN, "search"))
    assert '_total' in body, (
        "抖音没有回传 _total —— 前端无法显示真实条数，"
        "只能靠 total==len(results) 猜"
    )


def test_douyin_syntax_valid():
    ast.parse(_src(DOUYIN))


# =============================================================================
# 微博：写死的 has_more=False
# =============================================================================

def test_weibo_has_more_not_hardcoded_false():
    """微博的 `_has_more` 不能写死 False。"""
    body = _strip_comments(_search_body(WEIBO, "search_via_patchright"))
    assert 'out[0].raw_data["_has_more"] = False' not in body, (
        "微博仍写死 has_more=False —— 2026-10-03 实测微博**能翻页**"
        "（page1/2/3 各 10 条，重叠 0 个），写死等于把翻页入口藏起来"
    )
    assert "_has_more" in body, "微博应按实际是否取满来给出 has_more"


def test_weibo_syntax_valid():
    ast.parse(_src(WEIBO))


# =============================================================================
# 通用：不允许把"某次实测"写成永久结论而无复验标记
# =============================================================================

@pytest.mark.parametrize("p", [DOUYIN, WEIBO])
def test_stale_measurement_is_dated(p: Path):
    """平台行为会变：断言"平台没有第X页"的注释必须带实测日期。

    本仓库反复踩这个坑：抖音 09-27 能翻页、09-28 不能；
    微博 09-29"不能翻"、10-03 实测能翻。注释不写日期，
    下一个维护者会当成永久事实。
    """
    body = _search_body(p, "search" if p is DOUYIN else "search_via_patchright")
    if any(k in body for k in ("没有第 2 页", "没有第2页", "不支持翻页", "已失效")):
        assert re_search_date(body), (
            f"{p.name} 里断言了『平台不支持翻页』但没写实测日期 —— "
            f"平台行为会变（抖音 09-27→09-28、微博 09-29→10-03 都变了）"
        )


def re_search_date(text: str) -> bool:
    """正文里是否出现 YYYY-MM-DD 形式的实测日期。"""
    return bool(re.search(r"20\d{2}-\d{2}-\d{2}", text))
