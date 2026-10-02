"""子回复、评论图片、平台健康度统计的回归测试（2026-10-01）。

## 本轮做的三件事

1. **子回复（楼中楼）** —— 各平台接口不同，且容易做错
2. **评论图片** —— 微博/抖音/X 实测都有，之前只有微博取了
3. **平台健康度统计** —— 读 `platform_event_logs` 算成功率
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


# =============================================================================
# 子回复
# =============================================================================

def test_base_has_get_replies():
    """基类要有 `get_replies`（可选方法）。

    ⚠️ 子回复**不是**"评论列表的下一页" —— 端点/参数/签名都可能不同：
        抖音：端点换 `/comment/list/reply/`，参数用 comment_id+item_id，
              **签名函数也不同**（sign_reply vs sign_datail）
        快手：端点换 `/photo/comment/sublist`，加 rootCommentId
        X   ：二级回复在**同一棵**树里，靠父 id 筛（不用额外请求）
    """
    from app.services.platforms.base import BasePlatformClient

    assert hasattr(BasePlatformClient, "get_replies")
    src = inspect.getsource(BasePlatformClient.get_replies)
    assert "NotImplementedError" in src, "基类默认应抛未实现（各平台自己实现）"


def test_douyin_reply_uses_different_signature():
    """**关键**：抖音子评论要用**不同的签名函数** `sign_reply`。

    ⚠️ 用错的话签名不匹配 → 返回空 body（表现为"没有回复"，极难排查）。
    """
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.get_comments_page)
    assert "is_reply" in src, "要区分主评论/子评论"
    assert "sign_comment_params" in src
    assert "COMMENT_REPLY" in src or "comment/list/reply" in src

    sign_src = inspect.getsource(
        __import__("app.services.platforms.douyin.sign", fromlist=["sign_comment_params"])
        .sign_comment_params
    )
    assert "sign_reply" in sign_src, "子评论要用 sign_reply"
    assert "sign_datail" in sign_src, "主评论要用 sign_datail"


def test_douyin_reply_params_use_comment_id():
    """抖音子评论的参数是 `comment_id` + `item_id`（**不是** aweme_id）。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.get_comments_page)
    assert '"comment_id"' in src, "子评论要用 comment_id 参数"
    assert '"item_id"' in src, "子评论要用 item_id 参数（不是 aweme_id）"


def test_kuaishou_reply_uses_int_root_id():
    """快手子评论的 `rootCommentId` 是 **int**（实测，传字符串可能被拒）。"""
    from app.services.platforms.kuaishou.client import KuaishouClient

    src = inspect.getsource(KuaishouClient.get_replies)
    assert "rootCommentId" in src
    assert "int(" in src, "rootCommentId 要转 int"
    assert "COMMENT_SUB_LIST" in src or "sublist" in src


def test_api_supports_parent_id():
    """统一接口要有 `parent_id` 参数（取子回复）。"""
    from app.api.v1 import comments

    src = inspect.getsource(comments.get_comments)
    assert "parent_id" in src
    # B站没有独立子回复接口 —— 要**如实说明**，不是返回空
    assert "B站的子回复" in src or "随顶层评论" in src


def test_api_replies_501_for_unsupported():
    """平台没实现子回复时要报 501（不是空列表）。"""
    from app.api.v1 import comments

    src = inspect.getsource(comments.get_comments)
    assert "NotImplementedError" in src
    assert "暂不支持单独取子回复" in src


# =============================================================================
# 评论图片
# =============================================================================

def test_platforms_extract_comment_images():
    """各平台要提取评论图片（有就取，没有就空 —— 不编造）。"""
    cases = [
        ("weibo", "WeiboClient", "large"),
        ("douyin", "DouyinClient", "image_list"),
        ("twitter", "TwitterClient", "get_replies_via_http"),
    ]
    for plat, cls_name, hint in cases:
        mod = __import__(f"app.services.platforms.{plat}.client", fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        # 微博/抖音在自己的方法里；X 在 search_http 模块里
        if plat == "twitter":
            from app.services.platforms.twitter import search_http
            src = inspect.getsource(search_http.get_replies_via_http)
        else:
            src = inspect.getsource(cls.get_comments_page)
        assert "images" in src, f"{cls_name} 没提取评论图片"


def test_comment_item_model_has_images():
    """统一响应模型要有 images 字段。"""
    from app.api.v1.comments import CommentItem

    fields = CommentItem.model_fields
    assert "images" in fields
    assert "reply_to" in fields


# =============================================================================
# 平台健康度统计
# =============================================================================

def test_stats_route_exists():
    from app.api.v1 import platform_stats

    assert hasattr(platform_stats, "router")
    src = inspect.getsource(platform_stats)
    assert "/{platform}/stats" in src


def test_stats_does_not_fabricate_data():
    """**关键**：没数据时要如实说"还没有数据"，不能编造/说成故障。"""
    from app.api.v1 import platform_stats

    src = inspect.getsource(platform_stats.platform_stats)
    assert "还没有数据" in src or "没有留存" in src
    assert "这不是「平台有问题」" in src


def test_stats_flags_insufficient_sample():
    """**关键**：样本不足时**不下稳定性结论**。

    ⚠️ 1 次失败 = 0% 成功率 —— 直接显示"该平台不稳定"是误导。
    """
    from app.api.v1 import platform_stats

    assert hasattr(platform_stats, "MIN_SAMPLE")
    assert platform_stats.MIN_SAMPLE >= 3
    src = inspect.getsource(platform_stats.platform_stats)
    assert "sample_sufficient" in src
    assert "不足以判断稳定性" in src


def test_stats_normalizes_platform_alias():
    """别名要归并（否则 `x` 和 `twitter` 会分成两组，统计被拆散）。"""
    from app.api.v1.platform_stats import normalize_platform

    assert normalize_platform("x") == "twitter"
    assert normalize_platform("tw") == "twitter"
    assert normalize_platform("wb") == "weibo"
    assert normalize_platform("ks") == "kuaishou"
    assert normalize_platform("dy") == "douyin"
    assert normalize_platform("bilibili") == "bili"
    # 已经是标准名的原样返回
    assert normalize_platform("douyin") == "douyin"


def test_stats_uses_platform_scene():
    """统计读的是 `scene='platform'` 的记录。

    ⚠️ 实测：这个表原本只记 LLM/图片等 AI 场景，
    **没有平台采集记录** —— 所以写入端也必须用同一个 scene 值，
    否则读了也永远是空。
    """
    from app.api.v1 import platform_stats

    read_src = inspect.getsource(platform_stats.platform_stats)
    write_src = inspect.getsource(platform_stats.record_platform_event)
    assert "scene = 'platform'" in read_src
    assert 'scene="platform"' in write_src


def test_crawler_records_platform_events():
    """采集流程要**记录事件**（否则统计永远没数据）。

    ⚠️ 成功和失败都要记 —— 只记成功的话成功率永远是 100%。
    """
    from app.api.v1 import crawler

    src = inspect.getsource(crawler.search_enhanced)
    assert "record_platform_event" in src
    assert "success=True" in src, "成功要记"
    assert "success=False" in src, "**失败也要记**（否则成功率永远 100%）"
    # 记录失败不能影响搜索（best-effort）
    assert "except Exception" in src


# =============================================================================
# 前端
# =============================================================================

def test_weibo_replies_gives_real_reason():
    """**关键**：微博子回复要给出**实测原因**，不是笼统"不支持"。

    实测（2026-10-01）两条路都不行：
      · 顶层评论的 `comments` 字段：20 条里 0 条带
      · `/comments/hotFlowChild`：返回 ok=0（需额外参数）
    交叉验证 MediaCrawler（★66k）同样只读 `comments`，
    且其 `ENABLE_GET_SUB_COMMENTS` 默认关着。

    → 要如实抛错并**保留这段说明**，不能返回空列表
      （后者会让用户以为"这条评论没人回复"）。
    """
    from app.services.platforms.weibo.client import WeiboClient

    src = inspect.getsource(WeiboClient.get_replies)
    assert "NotImplementedError" in src
    assert "hotFlowChild" in src or "hotFlow" in src, "要写清试过哪个端点"
    assert "不是" in src, "要区分「平台没开放」和「没有回复」"


def test_api_preserves_platform_reply_reason():
    """**回归**：统一接口要**保留平台自己给的原因**。

    ⚠️ 原来是硬编码一句"暂不支持"，把平台的具体说明**丢掉了** ——
    而各平台原因不同（微博是接口限制），这些信息对用户更有用。
    """
    from app.api.v1 import comments

    src = inspect.getsource(comments.get_comments)
    assert "except NotImplementedError as exc" in src, "要捕获异常内容"
    assert "str(exc)" in src, "要保留平台的原始说明"


def test_gap_doc_is_not_stale():
    """**关键回归**：GAP 文档不能**还在主张**已过时的结论。

    ⚠️ 2026-10-01 踩过：原稿写「评论采集完全没做」，
    但评论其实**已经做完了** —— 这类盘点文档如果不随代码同步，
    下一个 AI/协作者会照着过时结论去**重复实现**已有功能。

    ## ⚠️ 断言要排除"修正记录"本身

    文档里**故意**保留了 `~~原结论~~ → 已做` 这种划掉记录
    （让读者知道改过什么）。所以不能简单 grep 关键词 ——
    那会把"修正记录"误判成"过时内容"。
    这里只检查**没有被划掉的**行。
    """
    from pathlib import Path

    doc = Path(__file__).resolve().parents[2] / "docs" / "platform" / "GAP_ANALYSIS_2026-10-01.md"
    if not doc.exists():
        pytest.skip("盘点文档不存在")

    # 只留"没有删除线"的行 —— 划掉的是**历史记录**，不是当前主张
    live_lines = [
        ln for ln in doc.read_text(encoding="utf-8", errors="ignore").splitlines()
        if "~~" not in ln
    ]
    live = "\n".join(live_lines)

    # 不能还在主张"评论没做"
    assert "**评论采集** 完全没做" not in live
    # 不能还在主张"博主中心没有入口"
    assert "在「博主中心」没有入口" not in live
    # 应当记录了已完成的事实
    assert "评论" in live


def test_gap_doc_records_platform_limits():
    """盘点文档要记录**平台限制**（不是所有 ❌ 都是"漏做"）。

    ⚠️ 这类区分很重要：把"平台没这个接口"当成"待办"，
    会导致后来者反复尝试实现一个**不可能实现**的功能。
    """
    from pathlib import Path

    doc = Path(__file__).resolve().parents[2] / "docs" / "platform" / "GAP_ANALYSIS_2026-10-01.md"
    if not doc.exists():
        pytest.skip("盘点文档不存在")
    text = doc.read_text(encoding="utf-8", errors="ignore")

    # 快手的"缺口"要说明是平台限制
    assert "快手" in text
    assert "平台" in text and ("限制" in text or "没有" in text)
    # Telegram 评论无解要写清原因
    assert "MTProto" in text or "t.me/s" in text


def _crawler() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


def test_frontend_renders_comment_images():
    """前端要渲染评论图片（走反代，直接 src 会被防盗链拦）。"""
    src = _crawler()
    assert "c.images" in src
    assert "proxy/image" in src


def test_frontend_has_reply_entry():
    """有子回复的评论要给"查看 N 条回复"入口。"""
    src = _crawler()
    assert "查看" in src and "条回复" in src
    assert "parent_id" in src, "取子回复要传 parent_id"


def test_frontend_shows_stats():
    """体检面板里要显示历史稳定性。"""
    src = _crawler()
    assert "getPlatformStats" in src
    assert "healthStats" in src
    assert "最近" in src and "小时" in src
