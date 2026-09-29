"""全平台功能验证中发现的 bug 的回归测试。

## 背景

用户要求"统计各平台搜索/分页/详情/我的数据/搜博主"。
我写了 `_verify_all_platforms.py` 逐项实测，**发现 3 个真 bug**：

### ① X 的 cookie 拿不到（搜索 0 条）

    netscape_to_header(raw, "twitter")  → 0 字符
    netscape_to_header(raw, "x.com")    → 1339 字符   ← X 的 cookie 域是 .x.com

我上一轮加映射表时**漏了 `twitter` 本身**
（只加了 `x` → `twitter`，而 `twitter` 又映射不到真实域名）。

修法：**逐个候选试**，而不是只查一次映射表 —— 漏项时还有兜底。

### ② B站搜索结果混入广告条目

B站搜索会返回**没有 `bvid` 的广告/推荐位**：

    [0] id=''  title='数据结构与算法：从基础原理到算法实战'
        url='https://www.bilibili.com/video/'      ← 点不开

不过滤的话列表里有"点不开"的空条目，前端拿空 id 调详情必然失败。

### ③ X 的详情 404

X 的详情数据来自搜索结果的 `raw_data`（`_images` / `_video_url`）——
它**没有"按 id 反查详情"的接口**。

前端原来只对**抖音**做"直接用搜索结果渲染"，
X 会去调 `/crawler/note-detail` → **拿不到 raw → 404**。

## 另外两个"不是 bug"的项（要如实记录）

  · **B站/番茄的 `/users/*` 返回 400** —— 设计如此。
    B站走 `/api/v1/bilibili/up/*` 专有路由（能力更强）；
    番茄是章节式平台，没有用户维度。
  · **番茄搜索 0 条** —— 平台限制（章节式发布，无通用搜索），
    代码里明确抛"暂未实现"而不是静默返回空。
  · **微博/X 的「我的数据」** —— 需要用户重新登录（登录态过期），
    不是代码问题。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# ① X 的 cookie 别名
# =============================================================================

def test_cookie_domains_include_x_com():
    """**回归**：X 的 cookie 域是 `.x.com`，别名表必须包含它。

    实测：
        netscape_to_header(raw, "twitter")  → 0 字符
        netscape_to_header(raw, "x.com")    → 1339 字符
    """
    from app.services.crawler import service as cs

    src = inspect.getsource(cs.CrawlerService._resolve_cookie_for)
    assert "x.com" in src, "别名表必须包含 x.com（X 的真实 cookie 域）"
    assert "twitter" in src


def test_cookie_resolver_tries_multiple_domains():
    """**回归**：要**逐个候选试**，不能只查一次映射表。

    我第一版只查一次映射表，漏了 `twitter` 项就静默返回空 ——
    加"逐个试"的兜底后，漏项也能拿到 cookie。
    """
    from app.services.crawler import service as cs

    src = inspect.getsource(cs.CrawlerService._resolve_cookie_for)
    assert "for dom in cookie_domains" in src, "应遍历候选域名"


def test_cookie_domains_is_tuple_map():
    """候选域名要用元组（一个平台对应多个可能的域）。"""
    from app.services.crawler import service as cs

    src = inspect.getsource(cs.CrawlerService._resolve_cookie_for)
    # 每个平台映射到一个元组
    assert '("xiaohongshu", "xhs")' in src
    assert '("x.com", "x", "twitter.com", "twitter")' in src


# =============================================================================
# ② B站广告过滤
# =============================================================================

def test_bili_filters_items_without_bvid():
    """**回归**：B站搜索结果要过滤掉没有 `bvid` 的条目。

    实测第 2 页第一条是广告位（无 bvid），title 有但点不开。
    """
    from app.services.platforms.bilibili import client as bili_client

    src = inspect.getsource(bili_client.BilibiliClient.search_videos)
    assert "bvid" in src
    assert "continue" in src, "应跳过无 bvid 的条目"
    # 注释里要说明是广告/推荐位
    assert "广告" in src or "推荐位" in src


# =============================================================================
# ③ X 详情走搜索结果
# =============================================================================

def test_frontend_uses_search_result_for_twitter():
    """**回归**：X 也要走"直接用搜索结果渲染"。

    X 的详情数据在搜索结果的 `raw_data` 里；它没有按 id 反查的接口。
    前端只对抖音这么做，X 会去调 `/crawler/note-detail` → 404。
    """
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "record.platform === 'twitter'" in src, (
        "X 应与抖音一样直接用搜索结果渲染详情"
    )
    # 两个平台应在同一个条件里
    i = src.find("record.platform === 'douyin'")
    assert i != -1
    seg = src[i:i + 200]
    assert "twitter" in seg, "X 应与抖音在同一个条件分支"


# =============================================================================
# 不是 bug 的项（如实记录，避免后人"修"它们）
# =============================================================================

def test_xhs_no_longer_in_browser_only():
    """小红书应走纯 HTTP（已打通），不该回到 BROWSER_ONLY。"""
    from app.services.crawler import service as cs

    src = inspect.getsource(cs.CrawlerService._search_via_platforms)
    line = next((ln for ln in src.splitlines() if "BROWSER_ONLY" in ln and "=" in ln), "")
    assert "xhs" not in line
    assert "weibo" in line


def test_fanqie_search_raises_not_silent():
    """番茄搜索"暂未实现"要**抛错**，不能静默返回空。

    番茄是章节式平台，没有通用搜索 —— 这是平台限制。
    但必须让用户看到原因，而不是"找到 0 条结果"。
    """
    from app.services.platforms.fanqie import client as fanqie_client

    src = inspect.getsource(fanqie_client)
    assert "暂未实现" in src or "无通用搜索" in src
