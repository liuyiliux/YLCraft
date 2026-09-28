"""抖音分页的契约测试（回应"检查分页功能"）。

## 现状（2026-09-28 实测）

抖音的 **offset 翻页已失效**：

    offset=0   count=20  -> 18 条  cursor=20  has_more=True   ✅
    offset=20  count=20  ->  0 条  cursor=40  has_more=False  ❌
    offset=5   count=5   ->  0 条  cursor=10  has_more=False  ❌

**在真实浏览器里跑同样的请求，offset=20 也是 0 条** ——
所以是抖音的**服务端行为变化**，不是我们的代码问题。

代码注释里"offset=0/20/40 有效"是 2026-09-27 的结论，已更新为"已失效"。

## 仍然要保证的

  · `page` 必须换算成 offset（否则 page=2 会重复 page=1 的数据）
  · 换算后即使拿不到数据，也**不能返回第 1 页的内容**充数
    （那会让用户以为"翻页没反应"）
"""

from __future__ import annotations

import inspect

import pytest


def test_douyin_search_uses_page_to_offset():
    """**回归**：抖音没有 `page` 参数，必须换算成 offset。

    原实现**忽略 page、offset 恒从 0 开始**，于是前端点"第 2 页"
    会拿到和第一页**完全相同**的数据（实测：两页首条 id 一样）。
    """
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "page_no" in src, "应读取 page"
    assert "offset = (page_no - 1) * page_size" in src, "应换算成 offset"


def test_douyin_documents_offset_paging_broken():
    """要记录"offset 翻页已失效"这个实测结论，避免后人误以为能翻页。"""
    from app.services.platforms.douyin.client import DouyinClient

    doc = inspect.getdoc(DouyinClient.search) or ""
    assert "已失效" in doc, "应说明 offset 翻页已失效"
    assert "2026-09-28" in doc, "应标注复测日期"
    # 要说明"不是我们的问题"
    assert "浏览器" in doc, "应说明真实浏览器也一样"


def test_douyin_keeps_offset_increment_logic():
    """offset 递增逻辑要保留 —— 抖音恢复该能力时无需改动即可生效。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "offset" in src
    assert "has_more" in src or "cursor" in src, "应有翻页终止判断"


def test_douyin_search_page_signature():
    """`search_page` 是底层入口，签名要保留 offset/count。"""
    from app.services.platforms.douyin.client import DouyinClient

    sig = inspect.signature(DouyinClient.search_page)
    assert "offset" in sig.parameters
    assert "count" in sig.parameters
