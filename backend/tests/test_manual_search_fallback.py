"""「去官网搜」（手动搜索跳转）的回归测试（2026-09-29）。

## 起因

用户反馈小红书触发风控（**HTTP 461**），并提议：

    "加一个搜索跳转 让我手动搜"

## 定位：这是**降级路径**，不是替代品

程序化搜索被风控挡住时，至少给用户一个出口：
用浏览器打开该平台的**网页搜索页**，自己搜自己看。

  · ✅ 不受我们这边的风控影响（是真人浏览器操作）
  · ❌ 拿不到结构化数据（不能导入素材库、不能批量下载）

所以 UI 上明确标注「程序化搜索被风控时的备选」。

## URL 都是实测过的（不是猜的）

    小红书  HTTP 200  '美食 - 小红书搜索'      ✅
    B站     HTTP 200  '美食-哔哩哔哩'           ✅
    抖音    HTTP 200                            ✅
    快手    HTTP 200  '快手'                    ✅
    微博    需登录（浏览器里已登录，可用）
    知乎    需登录
    X       格式正确（我方网络访问不了，浏览器可用）

## 顺带确认的一件事：快手**没有可用的「我是谁」接口**

用户问"我的中心不是都实现了吗，直接调个接口看看"——
对其它平台成立，**快手不行**。实测：

    /rest/wd/user/profile      → {"result":2001,"error_msg":"...antispam need captcha"}
    /rest/wd/user/ownInfo      → 404
    /rest/wd/user/fullInfo     → 空
    /rest/wd/user/userInfo     → 404
    /rest/wd/user/profile?userId={真|假} → 都是 {"result":2}，无法区分

**连浏览器上下文里都被风控拦**。所以只能靠 cookie 判断登录态。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _src() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 手动搜索跳转
# =============================================================================

def test_manual_search_url_map_exists():
    """要有网页搜索页的 URL 模板表。"""
    src = _src()
    assert "MANUAL_SEARCH_URLS" in src


def test_manual_search_helper_exists():
    """要有构造函数。"""
    src = _src()
    assert "function manualSearchUrl" in src


def test_manual_search_covers_main_platforms():
    """主要平台都要有网页搜索页（风控时能降级）。"""
    src = _src()
    i = src.find("MANUAL_SEARCH_URLS")
    seg = src[i:i + 1600]
    # 至少覆盖这几个（含别名）
    for key in ("xhs", "dy", "douyin", "bili", "ks", "wb", "twitter"):
        assert f"{key}:" in seg, f"缺 {key} 的搜索页模板"


def test_manual_search_urls_are_verified():
    """URL 要用**实测过的**形态（各平台不一样，不能瞎写）。

    实测（2026-09-29）：
        小红书 /search_result?keyword=
        抖音   /search/{kw}
        B站    search.bilibili.com/all?keyword=
        快手   /search/video?searchKey=
        微博   s.weibo.com/weibo?q=
    """
    src = _src()
    i = src.find("MANUAL_SEARCH_URLS")
    seg = src[i:i + 1600]
    assert "search_result?keyword=" in seg, "小红书是这个形态"
    assert "search.bilibili.com/all?keyword=" in seg
    assert "/search/video?searchKey=" in seg, "快手用 searchKey"
    assert "s.weibo.com/weibo?q=" in seg


def test_manual_search_button_rendered():
    """搜索框旁边要有按钮。"""
    src = _src()
    assert "去官网搜" in src, "应有按钮文案"
    assert "manualSearchUrl(" in src, "按钮要调用构造函数"


def test_manual_search_encodes_keyword():
    """关键词要 **URL 编码**（中文/空格/特殊字符）。"""
    src = _src()
    assert "encodeURIComponent(keyword)" in src


def test_manual_search_opens_new_tab():
    """要在新标签打开（不离开当前页面）。"""
    src = _src()
    i = src.find("manualSearchUrl(platform, kw)")
    assert i != -1
    seg = src[i:i + 400]
    assert "window.open" in seg
    assert "_blank" in seg


def test_manual_search_guards_empty_keyword():
    """没输关键词要提示，不能打开一个空搜索页。"""
    src = _src()
    i = src.find("const url = manualSearchUrl")
    assert i != -1
    seg = src[max(0, i - 300):i]
    assert "先输入关键词" in seg or "if (!kw)" in seg


def test_manual_search_documented_as_fallback():
    """注释要写明这是**降级路径**，不是替代品（免得被当成正式功能）。"""
    src = _src()
    i = src.find("MANUAL_SEARCH_URLS")
    seg = src[max(0, i - 1400):i]
    assert "降级" in seg or "风控" in seg


# =============================================================================
# 快手没有可用的「我是谁」接口（记录事实，免得后人重试）
# =============================================================================

def test_kuaishou_no_usable_self_api():
    """记录：快手**没有**可用的「我是谁」接口。

    用户问"我的中心不是都实现了吗，直接调个接口看看"——
    对抖音/小红书/微博/X/B站成立，**快手不行**（实测）。

    这条测试的价值：把"试过了、不行"固化下来，
    免得后人（或下一个 AI）再花时间试同一批端点。
    """
    from app.services.cookies.platforms import kuaishou

    src = open(kuaishou.__file__, encoding="utf-8").read()
    # 不可用的端点要留档
    assert "antispam" in src, "要记录风控事实"
    assert "rest/wd/user/profile" in src, "要记录试过的端点"
    # 且**不能**在 detect 里用它们
    import inspect
    det = inspect.getsource(kuaishou.KuaishouDetector.detect)
    assert "rest/wd" not in det, "不该用被风控的端点做判据"
