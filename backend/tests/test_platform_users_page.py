"""博主中心前端页面的契约测试。

## 背景（2026-09-27）

用户要求做抖音/小红书的 UP主搜索 + 个人中心。后端接口已就绪
（`/api/v1/users/*`），本轮补前端面板 `/platform-users`。

## 用真实浏览器实测过（bsk + 用户已登录 Chrome）

    抖音：搜索「李子柒」→ 19 个用户，首个 5657.0万粉
          详情面板 → 4830.7万粉 / 1 关注 / 2.55亿获赞 / 774 作品
          作品 Tab → 20 条（1168.9万赞 / 703.0万赞 / 1251.2万赞…）
    小红书：搜索「美食」→ 20 个用户（吕小厨爱美食 140.9万粉、
            妞妞儿美食 195.3万粉、铭哥说美食 226.0万粉…）
            并正确显示「小红书号」

## 实测发现并修掉的两个前端 bug

### 1. 小红书连接识别不到（平台标识不一致）

`/api/v1/platforms` 返回小红书连接时用的是 **`xhs`**，
而 `/users/*` 接口的 platform 参数是 **`xiaohongshu`**。
页面只按 `xiaohongshu` 筛 → 显示"未找到小红书连接"，
**但连接其实是好的**（接口实测能搜到用户）。

修法：给每个平台声明 `connKeys`，两种标识都接受。

### 2. 切换平台没清空上次结果

切到小红书后表格里还是抖音搜出来的"李子柒"——
标签是小红书、数据是抖音，属于错位展示。
修法：切换平台时清空 users/selected/profile/videos/keyword。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"前端源码不在预期位置: {rel}")
    return p.read_text(encoding="utf-8", errors="ignore")


def _strip_line_comments(src: str) -> str:
    """去掉 // 行注释（注释里会提到曾经写错的写法，直接断言会被误伤）。"""
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("//")
    )


# =============================================================================
# 页面与路由
# =============================================================================

def test_page_exists():
    src = _read("pages/platform-users/index.tsx")
    assert "博主中心" in src
    assert "PLATFORMS" in src


def test_route_registered():
    src = _read("App.tsx")
    assert "platform-users" in src, "路由未注册"
    assert "PlatformUsersPage" in src, "未导入页面组件"


def test_menu_entry_registered():
    src = _read("components/layout/AppLayout.tsx")
    assert "/platform-users" in src, "菜单未加入"


def test_api_functions_exist():
    src = _read("api/index.ts")
    for fn in ("searchPlatformUsers", "getPlatformUserProfile", "getPlatformUserVideos"):
        assert fn in src, f"缺少 {fn}"


# =============================================================================
# 两个实测修掉的 bug（回归）
# =============================================================================

def test_platform_conn_keys_accept_xhs_alias():
    """**回归**：小红书连接在连接表里叫 `xhs`，用户接口参数叫 `xiaohongshu`。

    只按 `xiaohongshu` 筛会显示"未找到小红书连接"，但连接其实是好的。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "connKeys" in src, "应声明连接标识别名"
    i = src.find("const PLATFORMS")
    seg = src[i:i + 500]
    assert "'xhs'" in seg, "小红书必须接受 xhs 这个连接标识"
    assert "'xiaohongshu'" in seg, "也要支持完整名"


def test_platform_switch_clears_previous_results():
    """**回归**：切换平台要清空上次结果。

    否则会"用小红书标签展示抖音用户"，属于错位展示。
    """
    src = _read("pages/platform-users/index.tsx")
    # 找到监听 platform 的 effect
    i = src.find("}, [platform])")
    assert i != -1, "应有依赖 platform 的 effect"
    seg = _strip_line_comments(src[max(0, i - 1200):i])
    for setter in ("setUsers([])", "setSelected(null)", "setVideos([])"):
        assert setter in seg, f"切平台时应调用 {setter}"


def test_reads_connections_not_data():
    """**回归**：连接要从 `res.connections` 读（不是 res.data）。

    番茄灵感页曾因读 res.data 导致"未找到连接"。
    """
    src = _read("pages/platform-users/index.tsx")
    i = src.find("listPlatformConnections()")
    assert i != -1
    seg = _strip_line_comments(src[i:i + 900])
    assert "connections" in seg
    assert "res?.data" not in seg


def test_filters_active_connections_only():
    src = _read("pages/platform-users/index.tsx")
    assert "status === 'active'" in src, "应只取 active 连接"


# =============================================================================
# 抖音/小红书差异（关键正确性）
# =============================================================================

def test_douyin_uses_sec_uid():
    """**回归**：抖音必须用 sec_uid。

    实测数字 uid 打开主页是空页面；sec_uid 才正常。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "sec_uid" in src, "应传 sec_uid"
    # 加载详情时优先用搜索结果里的 sec_uid
    assert "user.sec_uid" in src


def test_theme_destructuring_is_correct():
    """**回归**：`useTheme()` 返回 `{ theme, themeId }`。

    解构成 `{ THEME }` 会得到 undefined（实测编译报
    `Property 'THEME' does not exist`）。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "const { theme: THEME }" in src, "应解构 theme 并重命名为 THEME"


def test_images_go_through_proxy():
    """图片要走 /api/v1/proxy/image（图床有防盗链）。"""
    src = _read("pages/platform-users/index.tsx")
    assert "/api/v1/proxy/image" in src


# =============================================================================
# 2026-10-02：用户报的三个问题（排序真实性 / 缺X / B站功能变少）
# =============================================================================

def test_twitter_in_platform_list():
    """**关键回归**：博主中心必须**有 X**。

    ⚠️ 后端 `twitter` 的 search_users / get_user_profile / get_user_videos
    **全都有**、`users.py::SUPPORTED` 也含 —— 只是前端下拉漏了。
    这是本仓库第 N 次犯"**后端做了前端没接**"。
    """
    src = _read("pages/platform-users/index.tsx")
    i = src.find("const PLATFORMS = [")
    assert i != -1
    seg = src[i:i + 3000]
    assert "value: 'twitter'" in seg, "博主中心的平台下拉里没有 X"
    assert "connKeys: ['twitter', 'x', 'tw']" in seg, (
        "X 的 connKeys 不完整（连接表可能用 twitter/x/tw 任一种）"
    )


def test_all_supported_platforms_have_ui_entry():
    """**核心防线**：后端支持的平台，前端下拉里**都要有**。

    这条能一次性防住"后端做了前端没接"这个反复出现的坑
    （X、快手、YouTube/Telegram、微博都犯过）。
    """
    from app.api.v1.users import SUPPORTED

    src = _read("pages/platform-users/index.tsx")
    i = src.find("const PLATFORMS = [")
    seg = src[i:i + 3000]

    # 排除纯别名（它们由正式名的 connKeys 覆盖）
    aliases = {"bilibili", "dy", "ks", "wb", "x", "tw", "xhs"}
    canonical = {p for p in SUPPORTED.keys() if p not in aliases}

    missing = [p for p in canonical if f"value: '{p}'" not in seg]
    assert not missing, (
        f"这些平台后端支持用户查询，但博主中心下拉里没有：{sorted(missing)}\n"
        "用户选不到 = 功能等于不存在。"
    )


# =============================================================================
# 排序真实性（防"假选项"）
# =============================================================================

def test_sort_consumers_are_known():
    """**关键**：记录哪些平台的 `search()` **真的消费排序参数**。

    ## 实测（2026-10-02）

    · B站 / YouTube：`search()` 里出现排序参数 ✅
    · 小红书：排序在 `search_api.py`（有 `resolve_sort`）
    · **抖音 / 快手 / 微博 / X / 番茄：完全不消费 `sort_by`**

    当前前端**也没给它们显示排序档位**，所以不算假选项 ——
    但**这是隐患**：谁给它们加个"最新/最热"下拉，用户点了**毫无反应**
    （本仓库铁律：**假选项比没有更糟**）。

    这个测试把"谁消费、谁不消费"钉下来：以后给不消费的平台加前端排序，
    这里会失败并提醒先实现后端。
    """
    import importlib

    from app.services.platforms.base import BasePlatformClient

    CONSUMES_SORT = {"bilibili", "youtube"}
    SORT_ELSEWHERE = {"xiaohongshu"}

    markers = ("sort_by", "order_sort", "orderby", "sort_field",
               "sortType", "sort_type")

    for plat in ("bilibili", "douyin", "kuaishou", "weibo", "twitter",
                 "youtube", "xiaohongshu", "fanqie"):
        mod = importlib.import_module(f"app.services.platforms.{plat}.client")
        cls = None
        for _n, o in vars(mod).items():
            if (inspect.isclass(o) and issubclass(o, BasePlatformClient)
                    and o is not BasePlatformClient):
                cls = o
                break
        if cls is None:
            continue
        src = inspect.getsource(cls.search)
        code = "\n".join(
            ln for ln in src.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )
        consumes = any(m in code for m in markers)

        if plat in CONSUMES_SORT:
            assert consumes, (
                f"{plat} 原本消费排序参数，现在不消费了 —— "
                "前端若还显示排序档位就是**假选项**"
            )
        elif plat in SORT_ELSEWHERE:
            assert not consumes, f"{plat} 的排序位置变了，请更新本测试"
        else:
            assert not consumes, (
                f"{plat} 现在消费排序参数了！请加进 CONSUMES_SORT，"
                "并同步前端（否则后端支持了但没入口 = 白做）"
            )


def test_bili_sort_passes_order_to_backend():
    """**关键回归**：博主中心的排序 Tag 必须**真把 order 传给后端**。

    ⚠️ 旧版 /up-analytics 有排序，合并时丢了。恢复时最容易
    **只加 UI 不传参** —— 那就是假选项。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "order: videoOrder" in src, (
        "排序 Tag 只是 UI，没把 order 传给后端 —— 假选项"
    )
    i = src.find("排序：")
    assert i != -1
    seg = src[i:i + 800]
    # 只该有三档（实测 pubdate/click/stow 生效）
    for v in ("pubdate", "click", "stow"):
        assert f"'{v}'" in seg, f"缺少排序档位 {v}"
    assert "'danmaku'" not in seg, "加了没验证过的档位"


# =============================================================================
# B站功能恢复（合集/收藏夹/加载更多）
# =============================================================================

def test_bili_series_and_favorites_restored():
    """**关键回归**：合集 + 收藏夹 tab 要恢复。

    ⚠️ `db03be3c` 把 `/up-analytics` 合并进博主中心时**丢了三样**：
    排序、合集 tab、收藏夹 tab。后端接口和 API 封装**一直都在**。
    用户反馈"以前东西比现在全" —— 记忆准确。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "getBiliUpSeries" in src, "合集接口没接回来"
    assert "getBiliFavorites" in src, "收藏夹接口没接回来"
    assert "key: 'series'" in src and "key: 'favorites'" in src


def test_bili_extra_tabs_are_bili_only():
    """**关键**：合集/收藏夹**只能给 B站**。

    ⚠️ 别的平台后端没有这两个接口 —— 给它们显示就是**假 tab**
    （点开永远空，用户以为坏了）。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "platform === 'bili' ? [" in src, (
        "合集/收藏夹没被 platform === 'bili' 包起来"
    )


def test_favorites_requires_conn_id():
    """**回归**：收藏夹接口**必须要 conn_id**（实测不传返回 400）。

    要**提前检查 + 给可操作提示**，而不是让用户撞一个 400 报错。

    ⚠️ 2026-10-07 两处调整：
    1. 函数名 `getBiliFavorites(` → `getBiliUpFavorites(`
       （原来那个取的是**登录账号自己**的收藏夹，所以搜谁都是"我的"；
        现在取**被搜索那个 UP** 的公开收藏夹）。
    2. **不再要求 `!connId` 字面量出现在调用点附近** ——
       前置提示写在连接选择区（"未找到…连接 —— 请先到「账号中心」获取并保存登录态"），
       那里离调用点有两千多行。原来用"字符串是否在附近出现"来断言，
       会因为改版式而误报。改为断言**真正的不变量**：
       调用要传 conn_id，且界面上确实存在可操作的前置提示。
    """
    src = _read("pages/platform-users/index.tsx")
    i = src.find("getBiliUpFavorites(")
    assert i != -1, "收藏夹没有走「目标 UP 的公开收藏夹」接口"
    seg = src[max(0, i - 900):i + 200]
    assert "connId" in seg or "conn_id" in seg, "没传 conn_id"

    # 前置提示：连接为空时要告诉用户去哪儿配
    assert "账号中心" in src, "没有『请先到账号中心』这类可操作提示"


def test_favorites_shows_target_up_account():
    """**诚实性**：要说明收藏夹是**被搜索那个 UP** 的公开收藏夹。

    ⚠️ 2026-10-07 反转了断言方向。
    原测试要求源码里出现「未开放 / 你自己账号」—— 那句话是**错的**，
    害得界面上一边显示别人的收藏夹、一边写着"这是你自己的"（自相矛盾）。
    实测 `/bilibili/up/{uid}/favorites` 可用，能拿到该 UP 空间页上
    公开的那几个收藏夹（uid=50908119 → 默认收藏夹 557 / bgm 1）。
    ⇒ 现在**必须**说明是"该 UP 主公开的收藏夹"，且**不许**再出现旧说法。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "该 UP 主公开的收藏夹" in src, "没说明收藏夹属于被搜索的 UP"
    assert "未开放" not in src, (
        "还留着「B站未开放查看他人收藏夹」的错误说明"
    )


def test_series_rowkey_has_index_fallback():
    """**回归**：合集列表 rowKey 要能兜底。

    ⚠️ 2026-10-07 修正注释：接口打通后 `meta.season_id` 已能正常解析
    （实测 420975 等），"首条 id/title 都是空串"是**接口报错时**的表现。
    index 兜底仍然保留，所以断言不变。
    """
    src = _read("pages/platform-users/index.tsx")
    i = src.find("key: 'series'")
    assert i != -1
    seg = src[i:i + 2500]
    assert "series-${i}" in seg, "合集 rowKey 没有 index 兜底"


def test_videos_paginate_for_bili_and_keep_load_more_otherwise():
    """**关键回归**：作品列表的翻页要**按平台能力**分两种（2026-10-07）。

    · B站：`/bilibili/up/videos` 返回 `{list,total,page,page_size}`，
      能**真跳页**、能显示「共 N 个」⇒ 用 antd 分页 + 自己重新请求。
    · 其它平台走 `/users/videos`，**没有 page、没有 total**，
      只有 max_results ⇒ 只能「加载更多」，用 antd 分页是假的。

    ⚠️ 旧测试要求 `pagination={false}`（"别用假分页"）——
    现在 B站 恰恰**要**用分页，因为后端真支持；假分页的问题
    由 `loadVideoPage` 自己重新请求来解决（而不是靠关掉分页器）。
    """
    src = _read("pages/platform-users/index.tsx")

    # B站：真分页 + 用 total
    assert "loadVideoPage" in src, "B站 没有按页重新请求的逻辑"
    assert "videoTotal" in src, "没有保存后端返回的总数"
    assert "onChange: (pg: number) => void loadVideoPage(pg)" in src, (
        "antd 分页的 onChange 没有触发重新请求 —— 点了还是旧数据"
    )
    i = src.find("dataSource={videos}")
    assert i != -1
    seg = src[i - 200:i + 1400]
    assert "platform === 'bili' && videoTotal" in seg, "B站 没有走真分页分支"

    # 其它平台：保留「加载更多」
    assert "loadMoreVideos" in src, "其它平台的加载更多被误删了"
    assert "videoHasMore" in src, "没有'还有更多'状态"
    assert "platform !== 'bili'" in src, "加载更多没有限定平台"


def test_videos_dedup_and_limit():
    """加载更多要**去重**（B站翻页会重复）**且有上限**（防限流）。"""
    src = _read("pages/platform-users/index.tsx")
    i = src.find("const loadMoreVideos")
    assert i != -1
    seg = src[i:i + 2200]
    assert "seen" in seg or "Set(" in seg, "加载更多没去重"
    assert "MAX_VIDEOS" in src, "没有上限保护"


# =============================================================================
# 样式（截图里的列被挤成竖排）
# =============================================================================

def test_tables_have_horizontal_scroll():
    """**样式回归**：表格要设 `scroll={{ x }}`。

    ⚠️ 用户截图：选中博主后左列只有 `span=13`（半屏），
    表格被压得极窄 → 表头「粉丝」「作品」**被挤成竖排文字**。
    设 `x` 会**横向滚动**而不是压扁列。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "scroll={{ x:" in src, "表格没有横向滚动（窄屏会把列压成竖排）"


def test_numeric_columns_do_not_wrap():
    """**样式回归**：数字列表头要 `whiteSpace: nowrap`。

    ⚠️ 不设的话「粉丝」会上下排（截图里的问题）。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "NUM_COL_STYLE" in src or "onHeaderCell" in src
    assert "whiteSpace: 'nowrap'" in src
