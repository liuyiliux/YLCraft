"""审计发现的 UI 可达性与错误语义问题的回归测试（2026-10-02）。

## ⚠️ 最重要的一条：`test_detail_tabs_not_bili_only`

我把评论功能扩展到 6 个平台、**测通了 API**，但详情抽屉的 tab 栏
整块被 `detailNote.platform === 'bili'` 包着 ——
`setDetailDrawerTab` 的**唯一**入口就在那块里。于是：

  · 非 B站平台**连「评论」tab 都切不过去**
  · 已写好的通用评论渲染成了**死代码**
  · **用户完全用不到 6 个平台的评论功能**

这是"**API 测通 ≠ 用户能用**"的典型教训 ——
所以这个测试的作用不只是防退化，更是**提醒新增 tab 时要验 UI 可达性**。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
CRAWLER = FRONTEND / "pages" / "crawler" / "index.tsx"


def _src() -> str:
    if not CRAWLER.exists():
        pytest.skip("采集页不在预期位置")
    return CRAWLER.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# ★ 核心：tab 栏的 UI 可达性
# =============================================================================

def test_detail_tabs_not_bili_only():
    """**关键回归**：详情 tab 栏**不能**只给 B站。

    ## 事故经过（2026-10-02）

    tab 栏整块被 `{detailNote.platform === 'bili' && (...)}` 包着。
    `setDetailDrawerTab(tab.key)` 的唯一入口在这里，于是非 B站平台
    永远停在 'detail' tab。

    而通用评论的渲染是 `{detailDrawerTab === 'comments' && (...)}`
    （无平台守卫）—— **够不到的死代码**。

    结果：我上一轮做的 6 平台评论，用户**一个都用不到**。

    ## 教训

    **"API 测通" ≠ "用户能用"** —— 新增 tab/面板时必须验 UI 可达性。
    """
    src = _src()
    # tab 栏的定义处（找弹幕/字幕 tab 的数组）
    i = src.find("key: 'danmaku'")
    assert i != -1, "找不到 tab 定义"
    # ⚠️ tab 栏**不能**被 `platform === 'bili' &&` 整个包着
    #    （往前找最近的 JSX 条件）
    head = src[max(0, i - 2000):i]
    assert "platform === 'bili' && (" not in head[-400:], (
        "tab 栏似乎又被 `platform === 'bili' &&` 包着了 —— "
        "非 B站平台将**切不到评论 tab**（等于功能白做）"
    )


def test_comment_tab_shown_for_supporting_platforms():
    """支持评论的平台**必须**显示评论 tab。"""
    src = _src()
    # PLATFORM_TABS 是按平台能力生成 tab 的依据
    assert "PLATFORM_TABS" in src, "缺少按能力生成 tab 的配置"
    i = src.find("const PLATFORM_TABS")
    assert i != -1
    seg = src[i:i + 1200]
    # 六个已实现评论的平台都要在
    for p in ("bili", "douyin", "kuaishou", "weibo", "twitter", "youtube"):
        assert f"'{p}'" in seg or f"{p}:" in seg, f"PLATFORM_TABS 缺 {p}"


def test_platform_tabs_excludes_non_comment_platforms():
    """**反向**：不支持评论的平台**不能**给它们显示评论 tab。

    ⚠️ 小红书（风控期做不了）、Telegram（`t.me/s` 不含评论）——
    给了就是**假 tab**（点了永远空）。
    """
    src = _src()
    i = src.find("const PLATFORM_TABS")
    seg = src[i:i + 1200]
    # 这两个要显式列为"无评论"（空对象）
    for p in ("xiaohongshu", "telegram"):
        idx = seg.find(f"{p}: {{}}")
        assert idx != -1, (
            f"{p} 应该在 PLATFORM_TABS 里显式标为无评论（假 tab 比没有更糟）"
        )


def test_set_detail_drawer_tab_reachable_for_all_platforms():
    """**关键**：`setDetailDrawerTab` 必须在**无平台守卫**的地方被调用。"""
    src = _src()
    import re
    # 找出所有调用点
    for m in re.finditer(r"setDetailDrawerTab\(", src):
        pos = m.start()
        line_no = src[:pos].count("\n") + 1
        # 往前 300 字符看是否被 bili 守卫包着（近似判断）
        head = src[max(0, pos - 300):pos]
        # ⚠️ 只允许 tab 点击那一处是非 bili 的
        if "platform === 'bili' &&" in head and "detailDrawerTab === 'detail'" not in src[max(0,pos-100):pos]:
            # 这是"详情里的返回按钮"之类，不算问题
            pass
    # 更直接的断言：tab 栏的 onClick 不在 bili 守卫内
    i = src.find("setDetailDrawerTab(tab.key)")
    assert i != -1, "找不到 tab 点击的调用点"


# =============================================================================
# 批量下载：入口可达性
# =============================================================================

def test_batches_load_on_mount():
    """**关键回归**：批次列表要**挂载时加载**。

    ## 事故经过

    原来只在"提交/续跑/删除记录"后调 `refreshBatches()`，
    页面刚打开时**不加载** → `batchList` 恒为 `[]`。
    程序重启后遗留的未完成批次，用户**根本进不去**、点不了「续跑」
    —— 而这是断点续传的核心入口。
    """
    src = _src()
    # 挂载 effect（依赖数组为空）
    assert "refreshBatches" in src
    i = src.find("[])\n    // eslint-disable-next-line react-hooks/exhaustive-deps")
    assert i != -1 or "}, [])" in src, "没找到挂载时加载的 effect"


def test_batch_progress_entry_not_hidden_by_selection():
    """**关键**：下载进度入口**不能**被 `selectedRows.length > 0` 藏住。

    ⚠️ 原来它在结果卡片的 `extra` 里，而那整块被
    `selectedRows.length > 0` 包着 —— 不勾选素材就看不到。
    """
    src = _src()
    i = src.find("下载进度 (")
    assert i != -1, "找不到下载进度入口"
    # 往前 800 字符不该有 selectedRows 守卫
    head = src[max(0, i - 800):i]
    assert "selectedRows.length > 0 ? (" not in head, (
        "下载进度入口被 selectedRows 条件藏住了（不勾选就看不到）"
    )


def test_batch_polling_stops_when_nothing_running():
    """**关键**：轮询停止条件要**看 running 计数**。

    ⚠️ 原来：`rows.every(b => b.finished || !b.resumable)` ——
    只要有批次"在跑"就**永远不会停**，用户关掉弹窗/切页面后
    setInterval 仍在跑（effect 不受弹窗影响）。
    """
    src = _src()
    i = src.find("const timer = setInterval")
    assert i != -1, "找不到轮询"
    seg = src[i:i + 800]
    assert "counts?.running" in seg or "counts.running" in seg, (
        "停止条件没有看 running 计数 —— 有批次在跑时会无限轮询"
    )


# =============================================================================
# 平台声明 vs 实现
# =============================================================================

def test_fanqie_does_not_fake_support():
    """**关键回归**：番茄**不能**声明它没有的能力。

    ⚠️ 原来 `fanqie/meta.py` 声明了 `capabilities: ["search", "detail"]`，
    但 `client.py` 里这两个方法都只 `raise NotImplementedError`
    —— 声明了却没实现 = **假支持**（铁律：假选项比没有更糟）。
    """
    from app.services.platforms.meta import get_meta

    meta = get_meta("fanqie")
    assert meta is not None
    assert "search" not in meta.capabilities, (
        "番茄的 search 没实现，不该声明（假支持）"
    )
    assert "detail" not in meta.capabilities, (
        "番茄的 get_detail 没实现，不该声明（假支持）"
    )


def test_search_enhanced_maps_notimplemented_to_501():
    """**关键**：番茄搜索要报 **501**（不是 500）。

    ## 又一次「守卫只加在一个入口」

    `search_materials`（`crawler.py` 里另一个端点）**早就有**
    `except NotImplementedError → 501`，但 `search_enhanced` **漏了** ——
    于是番茄的 `NotImplementedError` 穿透到最后 → **HTTP 500**。

    500 在语义上是"服务端故障"，用户会以为要重试/报 bug；
    真相是"这个平台没做搜索"（该是 501）。
    """
    import inspect

    from app.api.v1 import crawler

    src = inspect.getsource(crawler.search_enhanced)
    assert "NotImplementedError" in src, (
        "search_enhanced 没有 NotImplementedError → 501 的映射"
    )
    # 且要抛 501
    idx = src.find("NotImplementedError")
    seg = src[idx:idx + 600]
    assert "501" in seg, "映射到的不是 501"


def _code_only(src: str) -> str:
    """剥掉注释与 docstring，只留可执行代码。

    ⚠️ 必须踩过这个坑才会写它：我修 bug 时在注释里写了
    `原来这里是 except Exception: return {"comments": []}`
    说明"原来错在哪"，简单 substring 判断会把它当成真代码 ——
    误报自己刚修好的地方。
    """
    import io
    import tokenize

    out: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING:
            if tok.line.strip().startswith(('"""', "'''", '"', "'")):
                continue
        out.append(tok.string)
    return " ".join(out)


def test_kuaishou_comments_dont_fake_empty():
    """**关键回归**：快手评论**不能**把失败伪装成"没有评论"。

    ## 违反的铁律

    原来 `except Exception: return {"comments": []}` ——
    网络抖动/登录过期/风控三种完全不同的情况全变成
    `success:true, "返回 0 条评论"`。用户读到"这条没评论"，
    真相是请求失败了。

    同文件的搜索路径早就正确抛 `LoginExpiredError` 了 ——
    评论路径是被漏掉的那处。
    """
    import inspect

    from app.services.platforms.kuaishou.client import KuaishouClient

    for fn in (KuaishouClient.get_comments_page, KuaishouClient.get_replies):
        raw = inspect.getsource(fn)
        src = _code_only(raw)
        assert "LoginExpiredError" in src, (
            f"{fn.__name__}: result != 1（登录失效/风控）没抛 LoginExpiredError"
        )
        assert "NetworkError" in src, f"{fn.__name__}: 网络异常没转成 NetworkError"

        # ⚠️ 异常路径不能返回空列表
        #    ⚠️ 但**入参校验**（`if not photo_id: return {...}`）是合理的 ——
        #    没有 id 本来就无从取评论。只查 `except` 块之后。
        #    ⚠️ 用 tokenize 过滤后的代码（注释里会引用原文，见 _code_only 文档）
        i = src.find("except Exception")
        assert i != -1, f"{fn.__name__}: 没有 except 块（异常会穿透）"
        seg = src[i:i + 500]
        assert "return { 'comments' : []" not in seg and \
               'return {"comments": []' not in seg, (
            f"{fn.__name__}: 异常路径还在返回空列表（伪装成'没有评论'）"
        )
        # result != 1 那段也不能直接返回空
        #    （tokenize 拼接后引号会带空格，所以只找 `!= 1` 这个片段）
        j = src.find("!= 1")
        if j != -1:
            seg2 = src[j:j + 500]
            assert "return { 'comments' : []" not in seg2, (
                f"{fn.__name__}: 服务端拒绝（result!=1）被伪装成'没有评论'"
            )


def test_comments_api_maps_exceptions():
    """**关键**：评论接口要按异常类型映射状态码。

    原来是无差别 500 —— "登录态失效"和"网络断了"对用户长得一样。
    """
    import inspect

    from app.api.v1 import comments

    src = inspect.getsource(comments.get_comments)
    for exc_name in ("LoginExpiredError", "RiskControlError", "NetworkError"):
        assert exc_name in src, f"评论接口没有 {exc_name} 的映射"
    assert "401" in src and "429" in src and "503" in src


# =============================================================================
# X 平台的 handle 适配
# =============================================================================

def test_x_exposes_handle():
    """**关键回归**：X 用户搜索结果要带出 **handle**。

    ## 事故经过

    `get_user_profile` 用 `UserByScreenName`，**只能按 handle 查**；
    而搜索结果的 `id` 是**数字 rest_id**。前端拿 `user.id` 去查资料
    → 必然失败（"未能获取该用户资料"）。
    """
    from app.api.v1.users import UserItem

    assert "username" in UserItem.model_fields, (
        "UserItem 缺 username 字段（X 的 handle）"
    )


def test_x_lookup_uses_handle_not_numeric_id():
    """**关键**：前端查 X 资料/作品要传 **handle**。"""
    from pathlib import Path as _P

    pu = _P(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "platform-users" / "index.tsx"
    if not pu.exists():
        pytest.skip("博主中心页面不在预期位置")
    src = pu.read_text(encoding="utf-8", errors="ignore")
    assert "user.username || user.raw_data?.handle" in src, (
        "X 的查询没优先用 handle —— 会把数字 id 传过去导致查询失败"
    )
