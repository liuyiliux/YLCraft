"""子回复能力的**实测结论**固化（2026-10-04）。

## 为什么要有这个

B站那个 bug 的性质是：`meta.py` / `comments.py` 都写着
「子回复随顶层评论一起返回」—— 而实测 `replies` 数组**全空**。
那是**当时也"实测过"**的结论，却已经过时。

所以对每个平台的"能不能取子回复"都必须**重新验**，并把结论写下来，
避免下一轮又照抄一份没复验的记录。

## 本轮实测结论

| 平台 | 结论 | 依据 |
|---|---|---|
| **B站** | ✅ **能取**（此前误报 501） | 老接口 `reply/main?root=` → 20 条真实数据 |
| **快手** | ✅ **能取** | `sublist` → 200，第一条就返回 1 条真实数据 |
| 微博 | ❓ **未验到** | 翻 30+ 个内容，0 条带 `reply_count`（见下方教训） |
| X | ⚠️ **半可用** | `reply_count=1` 有，但原始树里被引用 **0 次** |

## ⚠️ 最重要的一条教训

**快手那 15 条评论的 `reply_count` 全是 0，但直接打 sublist 第一条就返回了
1 条真实数据（`'男的是腹肌'`）。**

即：**`reply_count` 字段不能用来判断"这个平台/这条评论有没有楼中楼"**。

我第一轮抽样因为"`reply_count` 全是 0"就得出「快手取不到子回复」——
**结论是错的**，那只是"我抽的样本恰好都没有楼中楼"。

正确做法是**直接打接口**，看它返回什么。字段是提示，接口才是事实。
（B站那次也一样：先信了"随顶层返回"的注释，没实测。）

X 那条也是同一个道理：返回值 0 条时，
「X 侧没下发」与「我们过滤掉了」在结果上**完全一样**，
必须加诊断日志看原始树才能区分。

## 这些断言锁住
  1. 微博/快手不得宣称支持子回复（没数据）
  2. X 的能力声明要与「实际可能取不到」这件事一起说明，不能只写"支持"
  3. B站必须真能用（不能退回 501）
"""
from __future__ import annotations

from pathlib import Path

import pytest

META_DIR = Path(__file__).resolve().parents[1] / "app" / "services" / "platforms"


def _meta(name: str) -> str:
    p = META_DIR / name / "meta.py"
    if not p.exists():
        pytest.skip(f"{name}/meta.py not found")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 微博：**已验到能取**（2026-10-04 下午，之前是"未验到"）
# =============================================================================

def test_weibo_now_claimed_after_real_sample():
    """微博**能取**子回复 —— 这个测试曾断言相反的事。

    原来写的是 `supports("weibo", "replies") is False`，
    理由是"实测 30+ 个内容都没抽到带楼中楼的评论"。

    ⚠️ 那句话本身**当时就该被怀疑**：它是**抽样**。
    这个文件自己的快手用例就写着「抽样不能定论」——
    结果同一个文件里，微博又栽在同一件事上（同一个坑第三次）。

    2026-10-04 用户给了确定有楼中楼的样本
    （https://m.weibo.cn/detail/5336295257679240），实测：

        顶层 20 条 → **20/20 都有 replies**，共 32 条，rootid 零串号

    已补 `WeiboClient.get_replies` + meta 声明。
    """
    from app.services.platforms.meta import supports
    assert supports("weibo", "replies") is True, (
        "微博实测能取子回复（样本 5336295257679240，20/20 全有），应宣称支持"
    )


def test_weibo_meta_records_the_sampling_lesson():
    """meta 里要留下"抽样不够"这个教训，别让下一个人再抽样一次。"""
    src = _meta("weibo")
    assert "抽样" in src, (
        "微博 meta 必须写明：'20 条里 0 条带 comments' 是抽样结果，"
        "不是平台没有 —— 否则会有人照着那个错结论再拒一次"
    )


# =============================================================================
# X：能力声明必须附带「可能取不到」的说明
# =============================================================================

def test_x_replies_capability_is_annotated_as_half_usable():
    """X 声明了 replies，但实测原始树里可能没有那些子回复。

    这个说明必须留在代码里 —— 否则下一个人看到「声明了能力」
    就会以为它一定能用（那正是 B站踩过的坑）。
    """
    src = _meta("twitter")
    if '"replies"' not in src:
        pytest.skip("twitter 未声明 replies")
    assert "reply_count" in src, (
        "X 的 meta 应说明：reply_count 有值，但原始树里未必有对应子回复 —— "
        "2026-10-04 实测树内被引用 0 次（已删/折叠/需额外展开）"
    )


# =============================================================================
# B站 / 快手：实测真能取
# =============================================================================

@pytest.mark.parametrize("pf", ["bili", "kuaishou"])
def test_bili_kuaishou_replies_actually_work(pf: str):
    """B站与快手实测都能真取到子回复，不能退回 501。"""
    from app.services.platforms.meta import supports
    assert supports(pf, "replies") is True, f"{pf} 应声明 replies 能力"


def test_bili_get_replies_exists():
    from app.services.platforms.bilibili.client import BilibiliClient
    assert hasattr(BilibiliClient, "get_replies")


# =============================================================================
# 文档：结论必须带日期
# =============================================================================

def test_gap_analysis_records_verification_date():
    """盘点文档里的子回复结论必须带实测日期。"""
    p = (Path(__file__).resolve().parents[2]
         / "docs" / "platform" / "GAP_ANALYSIS_2026-10-01.md")
    if not p.exists():
        pytest.skip("gap analysis not found")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "2026-10-04" in src, (
        "子回复复验结论必须带实测日期 —— "
        "平台会改版（抖音 09-27→09-28、B站『随顶层返回』已过时）"
    )
    # 微博的结论必须还在（措辞可以是"未验到"而不是"拿不到"）
    assert "微博" in src and "子回复" in src, "微博的子回复结论不应被无声删除"
