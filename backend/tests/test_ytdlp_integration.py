"""yt-dlp 集成回归测试（2026-10-01 修三个坑）。

## 三个坑（都是"库模式与 CLI 默认值不一致"导致的静默问题）

1. **`fragment_retries` 库模式默认 0**（CLI 是 10）
   → 我们**分片下载零重试**，任何分片抖动就整个失败。
   抖音/YouTube 这类 HLS/DASH 流受影响最大。

2. **`cookiefile` 会被 yt-dlp 退出时回写**（截断写 `'w'`）
   → 我们传的是 `CookieManager` 的**共享路径**，而数据库里的
   `cookie_content` 才是权威。回写会让两者分叉，排查极难。

3. **`total_bytes` 可能为 None**（HLS/DASH 常见）
   → 进度条一直 0%，用户以为卡死。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 1. 重试参数
# =============================================================================

def test_download_sets_retry_options():
    """**回归**：下载 opts 必须显式设重试参数。

    ⚠️ 实测确认这是**真 bug**（不是"可能有问题"）：
    yt-dlp 的 `fragment_retries` 在**库模式默认 0**、CLI 默认 10
    （`options.py` 的 default=10 是 CLI 层；
    `downloader/fragment.py` docstring 明写
    "Default is 0 for API, but 10 for CLI"）。

    我们是库调用 → 原来**分片下载零重试**。
    """
    from app.api.v1 import download

    src = inspect.getsource(download._ytdlp_download)
    for key in ("retries", "fragment_retries", "file_access_retries",
                "extractor_retries"):
        assert f'"{key}"' in src, f"缺 {key}（库模式默认 0，分片下载零重试）"


def test_quality_probe_sets_extractor_retries():
    """枚举清晰度也要重试（元数据接口会间歇抖动）。

    不重试会让"这个视频没有清晰度"变成假象。
    """
    from app.api.v1 import download

    # 找枚举清晰度的函数（含 skip_download 的那个）
    for name, obj in vars(download).items():
        if not callable(obj) or name.startswith("__"):
            continue
        try:
            src = inspect.getsource(obj)
        except Exception:
            continue
        if "skip_download" in src and "formats" in src:
            assert "extractor_retries" in src, (
                f"{name} 枚举清晰度没设 extractor_retries"
            )
            return
    pytest.fail("没找到枚举清晰度的函数")


# =============================================================================
# 2. cookie 临时副本
# =============================================================================

def test_cookie_is_copied_to_temp():
    """**回归**：cookie 要传**临时副本**，不能传共享路径。

    yt-dlp 退出时会 `save_cookies()` → `cookiejar.save()` →
    `open(filename, 'w')`（**截断写**）。传共享路径会让它
    覆盖 `CookieManager` 的文件、与数据库的权威内容分叉。
    """
    from app.api.v1 import download

    src = inspect.getsource(download._ytdlp_download)
    assert "tempfile" in src or "tmp_cookie" in src, (
        "cookie 要复制成临时副本（否则 yt-dlp 回写会污染共享文件）"
    )
    assert "shutil.copyfile" in src or "copyfile" in src


def test_temp_cookies_are_cleaned():
    """临时 cookie 副本必须清理（里面是登录凭证）。"""
    from app.api.v1 import download

    assert hasattr(download, "_cleanup_temp_cookies")
    src = inspect.getsource(download._cleanup_temp_cookies)
    assert "os.remove" in src
    # 下载函数里要在 finally 里调用
    src2 = inspect.getsource(download._ytdlp_download)
    assert "_cleanup_temp_cookies" in src2
    assert "finally" in src2, "清理要放在 finally（成功/失败都要清）"


# =============================================================================
# 3. 进度回退链
# =============================================================================

@pytest.mark.parametrize("d,want", [
    ({"downloaded_bytes": 50, "total_bytes": 100}, 50.0),
    # ⚠️ HLS/DASH 常见：total_bytes 为 None，只有 estimate
    ({"downloaded_bytes": 25, "total_bytes": None,
      "total_bytes_estimate": 100}, 25.0),
    # 分片流：按分片数
    ({"downloaded_bytes": 1000, "fragment_index": 3, "fragment_count": 10}, 30.0),
    # 都没有 → 如实返回 0（**不假装 100%**）
    ({"downloaded_bytes": 500}, 0.0),
    ({}, 0.0),
    # 除零保护
    ({"downloaded_bytes": 5, "total_bytes": 0}, 0.0),
    # 夹在 0~100
    ({"downloaded_bytes": 200, "total_bytes": 100}, 100.0),
])
def test_progress_fallback_chain(d, want):
    """**回归**：进度必须走**回退链**。

        total_bytes → total_bytes_estimate → fragment_index/count → 0

    直接读 `total_bytes` 会在分片流上一直得到 0%（进度条不动，
    用户以为卡死）。**都没有时如实返回 0**，不假装 100%。
    """
    from app.api.v1.download import ytdlp_progress_percent

    assert abs(ytdlp_progress_percent(d) - want) < 0.01


def test_progress_hook_is_wired():
    """进度 hook 要真的挂上（否则实时进度不会上报）。"""
    from app.api.v1 import download

    assert hasattr(download, "_make_progress_hook")
    src = inspect.getsource(download._ytdlp_download)
    assert "progress_hooks" in src, "下载 opts 要挂 progress_hooks"


def test_progress_hook_never_raises():
    """**进度上报绝不能导致下载失败** —— hook 内部必须吞异常。

    进度是"锦上添花"，下载成功才是目标。hook 里抛异常会中断整个下载。
    """
    from app.api.v1 import download

    src = inspect.getsource(download._make_progress_hook)
    assert "except Exception" in src, "hook 要吞掉自己的异常"
    assert "pass" in src

    # 实际跑一遍（传垃圾数据也不该炸）
    hook = download._make_progress_hook("nonexistent-task")
    hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": None})
    hook({})
    hook({"status": "finished"})
    hook("not-a-dict")  # 类型都不对也不该炸


# =============================================================================
# 4. YouTube 403：要如实说明，不能只甩一句 Forbidden
# =============================================================================

def test_youtube_403_gets_actionable_message():
    """**回归**：YouTube 取流 403 要给**可操作**说明。

    ## 实测（2026-10-01）

    YouTube **元数据/清晰度枚举是好的**（`extract_info(download=False)`
    一直成功），但**下载视频数据**会被拒：

        ERROR: unable to download video data: HTTP Error 403

    **裸 yt-dlp 也一样** → 这是 YouTube 对匿名下载的限制
    （需要登录 cookie / PO Token），**不是我们的 bug**。

    但直接把 `HTTP Error 403: Forbidden` 甩给用户是**没用的** ——
    他既不知道这是"没登录"还是"视频不存在"，也不知道该干嘛。
    所以要转成可操作的话术，并**明确指出"不是视频不存在"**。
    """
    from app.api.v1 import download

    src = inspect.getsource(download._ytdlp_download)
    assert "403" in src, "要专门识别 403"
    assert "YouTube 拒绝" in src or "拒绝了**视频数据**" in src
    # 必须点明"不是视频不存在"（否则用户会以为是坏链）
    assert "不是「视频不存在」" in src or "不是视频不存在" in src
    # 要给出路
    assert "登录 cookie" in src or "去官网" in src

