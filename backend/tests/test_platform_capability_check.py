"""能力层校验 + has_more 修复的回归测试（2026-09-29）。

## 起因

用户问"总结下一个平台加入都怎么做"。

本仓库**已经有** `docs/platform/ADDING_A_PLATFORM.md`
+ `scripts/check_platform_registry.py`（登记层校验）。
但本轮实测的四个 bug **全部属于"登记齐全、但功能没接通"**，
而登记层脚本**查不出来** —— 且都不报错：

  ① X 的「我的数据」选不到        → 前端下拉漏加
  ② 微博下面显示抖音的创作者数据  → `else` 无条件兜底
  ③ 搜索没有「下一页」            → 后端从没设 `has_more`
  ④ 下载的素材在库里找不到        → 建节点漏了 `owner_user_id`

所以给脚本加了**能力层检查**（第 5 节），并修了它抓出来的真问题。

## 脚本抓出的真 bug

`has_more` 缺失的不止 X —— **B站 / 抖音 / 微博全中**（实测 `_has_more` 都是 None）：

    bili      9 条  raw._has_more=None
    douyin    9 条  raw._has_more=None
    weibo     9 条  raw._has_more=None

但 B站/微博 `page=2` **能正常翻** —— 所以前端"没有下一页"是**假阴性**。

修法：
  · B站 —— 本页拿满 page_size 就 True
  · 抖音 —— 本页拿满 **且** 响应 has_more 才 True（其 offset 翻页服务端已失效，如实说 False）
  · 微博 —— **固定 False**（实测 page=2 返回 173 字节 HTML 错误页，
    真翻页依赖 since_id 而 cardlistInfo.since_id 是 None）—— 不编造
"""
from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


# =============================================================================
# has_more 要真的给
# =============================================================================

def test_bili_sets_has_more():
    """**回归**：B站搜索结果要给 `_has_more`。"""
    from app.services.platforms.bilibili import client as bili

    src = inspect.getsource(bili.BilibiliClient.search_videos)
    assert "_has_more" in src


def test_douyin_sets_has_more():
    """**回归**：抖音要给 `_has_more`（且**如实**反映服务端状态）。"""
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.DouyinClient.search)
    assert "_has_more" in src
    # 不能无脑 True —— 抖音 offset 翻页已失效
    assert "data.get(\"has_more\")" in src or "data.get('has_more')" in src


def test_weibo_sets_has_more_from_real_paging():
    """**回归**：微博的 `_has_more` 要按**实际能不能翻**给。

    ⚠️ **2026-10-04 推翻了这条测试原来锁的东西。**

    原来它锁 `_has_more = False`，理由是 2026-09-29 的实测：
        page=2 返回 173 字节 HTML 错误页，`cardlistInfo.since_id` 为 None
    → 于是"平台没有第 2 页"被当结论固化进测试。

    但 2026-10-03 复测**推翻**了这个结论 —— 微博搜索能翻页：

        page=1  10 条  ['5344437661075159', '5344073515796857', ...]
        page=2  10 条  ['5349942244934068', '5349941822098505', ...]
        page=3  10 条
        page1 ∩ page2 = **0 个**  ← 真实翻页，不是重复数据

    现在代码按"**翻页循环怎么退出的**"给 `_has_more`：

    · 被 want 截断（`_stopped_by_want`）→ 后面还有
    · 真的翻完了（某页没新内容 / 要求登录）→ 到底

    ⚠️⚠️ **2026-10-07 第三次修正（推翻整条测试的前提）**

    上面写的两种判据（`_stopped_by_want` / `len(out) >= want`）都建立在
    一个**已经不成立**的前提上：**搜索函数自己去翻页**。

    现在的语义是「**取第 N 页，就只取第 N 页**」——
    `max_results` 是"这一页的上限"，不是"总共要攒多少"。

    以前把这两个混为一谈，导致 `max_results=30, page=2` 会**接着往后翻**，
    攒够 30 条才停 ⇒ 返回的是第 2、3、4 页的混合（实测 23 条），
    而且**第 1 页那 10 条不见了** —— 用户翻页看到的是残缺的一页。

    ⇒ 现在 `has_more` 的判据换成**平台自己说的总页数**：

        有「共50页」→ has_more = (page < 50)      准确
        平台没说   → has_more = 这一页有没有内容   保守，不编
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb.search_via_patchright)
    assert "_has_more" in src
    # 现在按「平台说的总页数」判断，不再靠翻页循环的退出原因
    assert "_total_pages" in src, (
        "has_more 应该用平台自己说的总页数（共50页）判断，而不是猜"
    )
    # 不得回退成这两个（都是已被实测推翻的判据）
    assert '_stopped_by_want' not in src, (
        "不要用 _stopped_by_want —— 它假设'搜索函数自己翻页攒数据'，"
        "而现在取第 N 页就只取第 N 页"
    )
    assert '"_has_more"] = len(out) >= want' not in src, (
        "不要退回 len(out) >= want（微博一页 9~10 条不固定，会误判成'到底了'）"
    )
    assert '"_has_more"] = False' not in src, (
        "不要写死 _has_more=False —— 2026-10-03 实测微博能翻页"
    )


def test_x_sets_has_more_from_cursor():
    """**回归**：X 按"有没有 cursor"给 has_more。"""
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.search_via_http)
    assert "_has_more" in src
    assert "cursor_next" in src


def test_page_sized_platforms_covered():
    """**回归**：`_SEARCH_PAGED_PLATFORMS` 里每个平台都要真的设 has_more。"""
    sys.path.insert(0, str(BACKEND))
    from scripts.check_platform_registry import _SEARCH_PAGED_PLATFORMS

    missing = []
    for plat in sorted(_SEARCH_PAGED_PLATFORMS):
        d = BACKEND / "app" / "services" / "platforms" / plat
        if not d.is_dir():
            # bilibili 的目录名就是 bilibili
            continue
        joined = "\n".join(
            p.read_text(encoding="utf-8") for p in d.glob("*.py")
        )
        if "_has_more" not in joined:
            missing.append(plat)
    assert not missing, f"这些平台没设 has_more：{missing}"


# =============================================================================
# 校验脚本的能力层检查
# =============================================================================

def test_script_has_capability_checks():
    """**回归**：脚本要包含能力层检查（不只是登记层）。"""
    sys.path.insert(0, str(BACKEND))
    from scripts import check_platform_registry as cpr

    assert hasattr(cpr, "check_capability_layers"), "应有能力层检查函数"
    assert hasattr(cpr, "_MY_DATA_PLATFORMS")
    assert hasattr(cpr, "_SEARCH_PAGED_PLATFORMS")


def test_capability_check_scans_whole_platform_dir():
    """**回归**：要扫**整个平台目录**。

    微博的搜索实现在 `search_patchright.py` ——
    只扫 `search_api.py` / `client.py` / `search_http.py`
    会**误判成"没实现"**。
    """
    sys.path.insert(0, str(BACKEND))
    from scripts import check_platform_registry as cpr

    src = inspect.getsource(cpr.check_capability_layers)
    assert "glob" in src, "应遍历平台目录下所有 .py"


def test_capability_check_finds_my_data_dropdown():
    """能力检查要查「我的数据」下拉（X 就这样漏过）。"""
    sys.path.insert(0, str(BACKEND))
    from scripts import check_platform_registry as cpr

    src = inspect.getsource(cpr.check_capability_layers)
    assert "my-platform-data" in src


def test_capability_check_guards_creator_panel():
    """能力检查要查创作者中心的平台守卫（防串平台数据显示）。"""
    sys.path.insert(0, str(BACKEND))
    from scripts import check_platform_registry as cpr

    src = inspect.getsource(cpr.check_capability_layers)
    assert "CreatorCenterPanel" in src


def test_full_check_passes():
    """**端到端**：全量校验（放行已知缺口）应该通过。

    这条测试的价值：以后有人加平台漏了某层，这里会红。
    """
    r = subprocess.run(
        [sys.executable, "scripts/check_platform_registry.py", "--allow-known"],
        cwd=BACKEND, capture_output=True, text=True, encoding="utf-8",
        errors="ignore", timeout=180,
    )
    assert r.returncode == 0, (
        f"平台校验未通过：\n{r.stdout[-2500:]}\n{r.stderr[-800:]}"
    )
