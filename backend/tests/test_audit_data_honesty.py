"""审计发现的"假支持/假数据/静默失败"问题的回归测试（2026-10-02 续）。

第一部分（UI 可达性）见 `test_audit_fixes.py`；本文件覆盖**数据诚实性**与
**异常语义**两类。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"


def _fx(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"{rel} 不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 假支持
# =============================================================================

def test_tiktok_removed_from_accounts_backend():
    """**关键**：账号中心**不能**列 TikTok（后端没有采集客户端）。

    ## 假支持的样子

    用户能在账号中心看到 TikTok、点进去、粘贴 cookie、保存连接 ——
    一切正常。但**后端根本没有 TikTok 采集客户端**
    （`create_client('tiktok')` 报 Unsupported platform，
    `supported_platforms()` 里也没有，搜索页下拉也没有）。

    结果：建了连接**没有任何入口能用它**。
    仓库铁律：**假选项比没有更糟**。

    ⚠️ 注意：`connectors/social/tiktok` 是**另一套**（OAuth 发布连接器，
    16KB 真实存在），它保留是对的 —— 采集与发布是两回事。
    """
    from app.api.v1 import platforms

    vals = {p["value"] for p in platforms.SUPPORTED_PLATFORMS}
    assert "tiktok" not in vals, (
        "账号中心仍列 TikTok —— 但后端没有采集客户端（假支持）"
    )


def test_tiktok_removed_from_accounts_frontend():
    """前端也要删（它是硬编码的，与后端独立）。"""
    src = _fx("pages/accounts/index.tsx")
    i = src.find("const PLATFORM_METAS")
    assert i != -1
    seg = src[i:i + 3000]
    assert "value: 'tiktok'" not in seg, (
        "前端账号中心仍列 TikTok（假支持）"
    )


# =============================================================================
# 假数据
# =============================================================================

def test_my_data_has_no_fake_view_count():
    """**关键**：「总播放量」不能读 `profile.likes`。

    ## 假数据的样子

    审计发现：「总播放量」和「总点赞数」**读的是同一个字段**
    `profile?.likes`，而后端 `/bilibili/up/profile`
    **根本没有播放量字段**（只有 `fans`/`likes`/`following`）。

    也就是：
      · 两张卡显示**同一个数字**
      · 而且「总播放量」的值其实是**累计获赞**，量级完全不同
        → 用户会据此做出错误的内容判断

    B站的"获赞"是账号累计获赞，与播放量是完全不同的量级。

    ⚠️ 断言只查 `<Statistic title=...>` —— 因为文件里的注释
    **故意引用了「总播放量」这个词**来说明"原来错在哪"，
    简单 grep 会把它误判成"还没改"。
    """
    src = _fx("pages/my-data/index.tsx")
    # ⚠️ 只查真实的 UI label —— 文件里的注释**故意引用了**
    #    「总播放量」这个词来说明"原来错在哪"，简单 grep 会误判。
    #    用"title 属性的紧邻文本"来找（正则要允许 style 里的嵌套括号）。
    import re
    labels = set(re.findall(
        r"title=\{<Text[^>]*>\s*([^<>{]+?)\s*</Text>", src
    ))
    for kw in ("总获赞", "总关注", "总粉丝数", "视频总数", "总播放量", "总点赞数"):
        if kw in labels:
            assert kw != "总播放量", (
                "「总播放量」是捏造的指标（后端 /bilibili/up/profile 没该字段）"
            )
            assert kw != "总点赞数", (
                "「总点赞数」与「总获赞」重复（同一字段）"
            )
    for need in ("总获赞", "总关注", "总粉丝数", "视频总数"):
        assert need in labels, f"缺少「{need}」卡片；现有：{sorted(labels)}"
    # 至少两个不同字段（防止又出现两张卡读同一个值）
    assert "value={(profile as any)?.following || 0}" in src, (
        "「总关注」没读 following 字段（可能又与别的卡重复）"
    )


def test_my_data_cards_are_distinct():
    """**回归**：概览四张卡不能有两个读同一个字段。"""
    src = _fx("pages/my-data/index.tsx")
    i = src.find("数据概览")
    assert i != -1
    seg = src[i:i + 4000]
    # 统计 value={profile?.likes} 出现次数（应该只有 1 次 = 总获赞）
    likes_cards = seg.count("value={profile?.likes || 0}")
    assert likes_cards <= 1, (
        f"有 {likes_cards} 张卡读同一个 profile.likes（数据重复）"
    )


# =============================================================================
# 异常语义（该 401 的不能报 500）
# =============================================================================

def test_twitter_error_class_hierarchy():
    """**关键回归**：X 的异常必须能被 `except LoginExpiredError` 捕获。

    ## 事故经过

    `twitter/client.py` 和 `twitter/search_http.py` 各定义了一个
    **同名** `TwitterAuthError`：
      · `search_http.py` 的继承 `LoginExpiredError` ✅（2026-09-30 改的）
      · `client.py` 的只继承 `RuntimeError` ❌（**漏改**）

    而 `client.py` 抛的正是后者（用户搜索/资料/作品路径）——
    于是 API 层的 `except LoginExpiredError` **全部落空**，
    登录态过期时返回 **HTTP 500**「获取我的资料失败」。

    500 在语义上是"服务端故障"，用户不会想到要去账号中心重新登录
    —— 而这恰恰是用户自己能解决的问题。
    """
    from app.services.platforms.twitter.client import TwitterAuthError
    from app.services.platforms.types import LoginExpiredError

    assert issubclass(TwitterAuthError, LoginExpiredError), (
        "TwitterAuthError 必须继承 LoginExpiredError，否则 401 映射不生效"
    )


def test_weibo_error_class_hierarchy():
    """微博同理（`WeiboLoginRequiredError` 必须继承 `LoginExpiredError`）。"""
    from app.services.platforms.types import LoginExpiredError
    from app.services.platforms.weibo.client import WeiboLoginRequiredError

    assert issubclass(WeiboLoginRequiredError, LoginExpiredError), (
        "微博登录态失效会返回 500 而不是 401"
    )


def test_xhs_note_uses_typed_exceptions():
    """**关键**：小红书详情要用类型化异常，不能抛裸 `RuntimeError`。

    ## 谎报的问题

    461（风控）原本抛 `RuntimeError` → `crawler/service.py` 的
    `except Exception: return {}` 吞成空 dict → 路由层变成
    **404「笔记不存在」**。

    但 461 是**风控**，笔记**确实存在**（用户刚从搜索结果点进来）。
    用户会以为笔记被删了。

    抛 `RiskControlError` 后映射成 429 + 可操作提示。
    """
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod)
    assert "RiskControlError" in src, (
        "461 风控没抛 RiskControlError（会被吞成 404 谎报'笔记不存在'）"
    )
    assert "LoginExpiredError" in src, "缺 cookie 也没抛 LoginExpiredError"
    # 关键：不能再有裸 RuntimeError
    assert "raise RuntimeError" not in src, (
        "还有裸 RuntimeError —— 会被 service 层吞成 404"
    )


def test_service_lets_risk_control_pass_through():
    """**关键**：`get_note_detail` 的穿透列表要包含风控/网络类异常。

    ## "守卫只加在一个入口"的老坑

    穿透列表原来只有 `PlatformUnavailableError` + `LoginExpiredError`，
    而小红书的 461 抛的是 `RiskControlError` —— 不在列表里，
    于是被 `except Exception: return {}` 吞成 404。
    """
    from app.services.crawler.service import CrawlerService

    src = inspect.getsource(CrawlerService.get_note_detail)
    for exc in ("RiskControlError", "NetworkError", "ContentNotFoundError"):
        assert exc in src, (
            f"{exc} 没有穿透 —— 会被 `except Exception: return {{}}` "
            "吞成 404「笔记不存在」"
        )


def test_service_imports_all_error_types():
    """**关键**：穿透了却没 import = `NameError` 被 `except` 吞掉（静默失效）。

    ⚠️ 这是**最隐蔽**的一种：代码看着对，实际因为名字没导入
    而在运行到那一行时抛 `NameError`，然后被
    `except Exception: return {}` 吃掉 —— 修复"看起来生效了"其实没有。
    """
    from app.services.crawler import service as service_mod

    src = inspect.getsource(service_mod)
    for exc in ("RiskControlError", "NetworkError", "ContentNotFoundError",
                "LoginExpiredError"):
        assert exc in src, f"{exc} 没有导入 —— 运行时会 NameError"


# =============================================================================
# 静默失败
# =============================================================================

def test_fanqie_panel_distinguishes_load_error():
    """**关键**：番茄面板要区分"加载失败"和"确实没账号"。

    审计称这是**最主动误导**的一处：一次网络抖动 →
    `catch` 吞掉 → `connections` 保持 `[]` → 界面渲染
    「请先在账号中心添加番茄账号」→ 用户跑去账号中心发现
    **账号明明在**，回来更困惑。
    """
    src = _fx("pages/my-data/FanqieDataPanel.tsx")
    assert "connLoadError" in src, "没有区分'加载失败'与'没有账号'"
    # ⚠️ 断言用不完整的关键词（实际文案含"番茄"两个字）
    assert "不是「你没有番茄账号」" in src, (
        "没说明'加载失败 ≠ 没有账号' —— 用户会白跑一趟账号中心"
    )


def test_bili_stats_error_is_shown():
    """**关键**：B站数据统计失败要**显示原因**。

    原来 `catch {}` 静默吞掉 → 面板空白 → 用户会把"空白"
    读成"这个视频播放量是 0"，而真相可能是 401/429。

    ⚠️ 尤其危险：**空面板和"全是 0"在视觉上几乎一样**。
    """
    src = _fx("pages/crawler/index.tsx")
    assert "statsError" in src, "数据统计没有错误态"
    assert "不是「数据为 0」" in src or "请求失败" in src, (
        "没说明'这是请求失败，不是数据为 0'"
    )


def test_bili_video_info_error_is_shown():
    """视频信息失败也要显示（原来静默缺分区/UP主/发布时间）。"""
    src = _fx("pages/crawler/index.tsx")
    assert "videoInfoError" in src, "视频信息没有错误态"


# =============================================================================
# Telegram：后端做了前端没接
# =============================================================================

def test_telegram_channels_has_ui_entry():
    """**关键回归**：Telegram「我的频道」要有前端入口。

    ⚠️ 后端 `/telegram/channels` 早就实现了，登录页却只能
    "去采集"搜关键词 —— 看不到自己有哪些频道。
    """
    src = _fx("pages/telegram-login/index.tsx")
    assert "getTelegramChannels" in src, (
        "后端 /telegram/channels 已实现但前端没接（后端做了前端没接）"
    )
    assert "我的频道" in src, "没有'我的频道'入口"


# =============================================================================
# 断点续传：登记的 outtmpl 要真实
# =============================================================================

def test_platform_downloader_registers_empty_outtmpl():
    """**关键**：平台下载器路径登记的 `outtmpl` 要是**空串**。

    ## 踩坑经过

    原来传 `str(savedir / title)` —— 一个**普通路径**，不是
    yt-dlp 的 `%(title)s` 模板。而 B站的 `_stream_to_file`
    用的是 `<最终路径>.mp4.part` 约定。

    `_partial_size_for` 据此 glob 不到任何 `.part` →
    `bytes_done` 恒为 0 → `/download/resumable` 把它
    当成"没有可续传数据"（而实际上可能有半截文件）。

    传空串 = 如实表示"这条路径不按 .part 追踪"，
    `list_resumable` 会因为找不到半成品而过滤掉它（**不谎报**）。
    """
    import inspect as _i

    from app.api.v1 import download as dl

    src = dl.__file__ and open(dl.__file__, encoding="utf-8").read()
    # 找平台下载器路径的 _register_resumable 调用
    i = src.find("_resume_savedir")
    assert i != -1, "找不到平台下载器路径的登记"
    seg = src[i:i + 1200]
    j = seg.find("_register_resumable")
    assert j != -1
    call = seg[j:j + 400]
    # 最后一个参数应是空串（注释说明）
    assert '""' in call or "''" in call, (
        "平台下载器路径仍传了非空 outtmpl —— 会让 bytes_done 恒为 0"
    )


# =============================================================================
# 批次清理
# =============================================================================

def test_finished_batches_are_cleaned():
    """**关键**：`batches.json` 要有清理策略（防无限增长）。

    审计发现：只追加、从不清理，而 `update_item` 每次都要
    全量 `_load()` + `_save()`。500 条的批次会调 1500 次
    `update_item`，复杂度 O(批次总数 × 总条目) × 1500。

    已实现：创建批次时清理**已完成**的旧批次
    （保留最近 `KEEP_FINISHED_BATCHES` 个）。
    ⚠️ 未完成的**永不自动删** —— 那是用户的断点续传依据。
    """
    from app.api.v1 import download_batch as store

    assert hasattr(store, "KEEP_FINISHED_BATCHES")
    assert store.KEEP_FINISHED_BATCHES >= 5
    assert hasattr(store, "_is_all_done")
    src = inspect.getsource(store.create_batch)
    assert "_is_all_done" in src, "create_batch 没有清理已完成批次"
