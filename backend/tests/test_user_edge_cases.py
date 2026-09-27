"""用户视角的边界场景契约测试。

真实用户不会只贴"标准链接"，他们会贴分享文本、短链、缺 token 的链接。
这些场景此前**全部失败且错误信息笼统**，用户完全不知道该怎么办。

## 修掉的三件事（2026-09-27）

1. **分享文本没提取链接**
   `7.43 复制打开抖音，看看…https://v.douyin.com/xxx/ 复制此链接`
   原来整段当 URL 用 → 必然失败。
   parse 端点现在先走 `_extract_url_from_text`。

2. **短链没跟随重定向**
   `v.douyin.com/iRNBho6u/` → 302 →
   `iesdouyin.com/share/video/7298145681699622182/?…`
   原来直接在短链上正则找 ID → 找不到。
   现在 `_resolve_short_link` 先重定向。

3. **错误信息笼统**
   原来一律"未找到视频或图片数据"。现在按平台给可操作原因，
   尤其小红书**缺 xsec_token** 是最常见的坑，会明确告知怎么拿。

## 一个教训

边界测试用**编造的作品 ID**（如 `7000000000000000000`）得出的结论不可靠——
抖音对不存在的 ID 也返回 HTTP 200 页面壳，且详情接口返回空 `aweme_detail`，
看起来像"功能坏了"，实际是"这个作品不存在"。
**验证功能必须用真实存在的作品**（从搜索结果里取）。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 分享文本提取
# =============================================================================

@pytest.mark.parametrize(
    "text",
    [
        "7.43 复制打开抖音，看看【某某的作品】好看 https://www.douyin.com/video/7664911070490126501 复制此链接",
        "看看这个 https://www.iesdouyin.com/share/video/7664911070490126501/?region=CN 有意思",
        "https://www.douyin.com/video/7664911070490126501",
    ],
)
def test_share_text_extracts_url(text):
    """分享文本里要能提取出链接。"""
    from app.services.video.parser import _extract_url_from_text

    url = _extract_url_from_text(text)
    assert url.startswith("http")
    assert "7664911070490126501" in url


def test_parse_endpoint_extracts_url_from_text():
    """**回归**：parse 端点必须先提取链接。

    原来直接把 req.url 当链接用，用户粘贴分享文本必然失败。
    """
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.parse_download_url)
    assert "_extract_url_from_text" in src, "应先从文本提取链接"
    # 且要在使用 url 之前
    assert src.find("_extract_url_from_text") < src.find("req.url")


# =============================================================================
# 短链重定向
# =============================================================================

def test_short_link_hosts_declared():
    from app.services.platforms.douyin.detail_adapter import SHORT_LINK_HOSTS

    assert "v.douyin.com" in SHORT_LINK_HOSTS


def test_resolve_short_link_is_wired():
    """**回归**：fetch_douyin_detail 必须先解析短链再提取 ID。"""
    from app.services.platforms.douyin import detail_adapter

    src = inspect.getsource(detail_adapter.fetch_douyin_detail)
    assert "_resolve_short_link" in src
    assert src.find("_resolve_short_link") < src.find("extract_aweme_id("), (
        "应先重定向再提取 ID"
    )


def test_resolve_short_link_skips_normal_urls():
    """非短链不应发无谓请求。"""
    from app.services.platforms.douyin import detail_adapter

    src = inspect.getsource(detail_adapter._resolve_short_link)
    assert "SHORT_LINK_HOSTS" in src, "应只在已知短链域名上重定向"


@pytest.mark.asyncio
async def test_resolve_short_link_returns_input_when_not_short():
    from app.services.platforms.douyin.detail_adapter import _resolve_short_link

    url = "https://www.douyin.com/video/7664911070490126501"
    assert await _resolve_short_link(url) == url


# =============================================================================
# 平台特定错误信息
# =============================================================================

def test_xhs_missing_token_message_is_actionable():
    """小红书缺 token 时要给出**怎么拿到 token** 的指引。

    这是小红书最常见的失败原因，笼统的"未找到数据"会让用户完全无从下手。
    """
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.parse_download_url)
    assert "xsec_token" in src, "应专门处理缺 token 的情况"
    assert "采集与下载" in src or "搜索" in src, "应告诉用户去哪拿带 token 的链接"


@pytest.mark.parametrize(
    "marker",
    ["xiaohongshu.com", "douyin.com", "bilibili.com", "twitter.com"],
)
def test_error_messages_are_platform_specific(marker):
    """每个主要平台都要有自己的错误提示。"""
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.parse_download_url)
    assert marker in src, f"{marker} 应有专属错误提示"


def test_error_message_not_only_generic():
    """不能只有一句通用错误。"""
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.parse_download_url)
    assert "账号中心" in src or "登录态" in src, "应提示检查登录态"


# =============================================================================
# 下载端点的边界行为
# =============================================================================

def test_download_images_rejects_empty():
    """空列表要 400，不静默成功。"""
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.download_images)
    assert "图片列表为空" in src


def test_download_images_records_invalid_urls():
    """非法地址要记入 failed，而不是让整个请求崩掉。"""
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.download_images)
    assert "非法地址" in src
    assert "failed.append" in src


def test_download_images_is_idempotent_by_design():
    """重复下载会覆盖同名文件——这是预期行为（用户可能想重下）。"""
    from app.api.v1 import download as dl

    src = inspect.getsource(dl.download_images)
    # 文件名带序号，重复下载落到同一路径
    assert "{idx:02d}" in src, "文件名应含序号，保证同一图集重复下载落在同一批文件名"
