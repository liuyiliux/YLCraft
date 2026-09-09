"""小说下载器的并发与可取消行为。

背景：串行抓几百章曾把线程池与连接池占满、拖垮整个后端（停止响应）。
这里锁住并发版下载器的契约：成功/失败计数准确、文件按序号落盘、取消后不再抓新章节。
"""

import threading
import time

import pytest

from app.services.novel.downloader import NovelDownloader


def _chapters(count: int = 3):
    return [
        {"index": i + 1, "title": f"第{i + 1}章", "url": f"https://example.com/c/{i + 1}"}
        for i in range(count)
    ]


async def test_download_chapters_writes_files_and_counts(tmp_path):
    dl = NovelDownloader(output_dir=str(tmp_path))

    async def fetcher(url: str) -> str:
        return f"正文内容 {url}"

    result = await dl.download_chapters(
        book_title="测试书",
        author="某作者",
        chapters=_chapters(3),
        content_fetcher=fetcher,
        concurrency=3,
        delay=0,
    )

    assert result["success_count"] == 3
    assert result["failed_count"] == 0
    book_dir = tmp_path / "测试书"
    assert (book_dir / "0001_第1章.txt").exists()
    assert (book_dir / "0003_第3章.txt").exists()
    # 章节文件带标题行，便于后续按标题切分与本地阅读
    first = (book_dir / "0001_第1章.txt").read_text(encoding="utf-8")
    assert first.startswith("# 第1章")
    # 合并文件包含所有章节
    merged = (book_dir / "测试书_全集.txt").read_text(encoding="utf-8")
    assert "第1章" in merged and "第3章" in merged


async def test_download_chapters_counts_failures(tmp_path):
    dl = NovelDownloader(output_dir=str(tmp_path))

    async def fetcher(url: str):
        return None if url.endswith("/2") else "正文"

    result = await dl.download_chapters(
        book_title="测试书",
        author="某作者",
        chapters=_chapters(3),
        content_fetcher=fetcher,
        concurrency=3,
        delay=0,
    )
    assert result["success_count"] == 2
    assert result["failed_count"] == 1
    assert [item["index"] for item in result["success"]] == [1, 3]


async def test_download_chapters_respects_stop_event(tmp_path):
    dl = NovelDownloader(output_dir=str(tmp_path))
    stop_event = threading.Event()
    stop_event.set()  # 调用前已请求停止

    async def fetcher(url: str) -> str:
        raise AssertionError("停止后不应再抓取")

    result = await dl.download_chapters(
        book_title="测试书",
        author="某作者",
        chapters=_chapters(3),
        content_fetcher=fetcher,
        concurrency=2,
        delay=0,
        stop_event=stop_event,
    )
    # 已停止：既没有成功章节，也不该把未抓的章节算成失败
    assert result["success_count"] == 0
    assert result["failed_count"] == 0


async def test_download_chapters_runs_concurrently(tmp_path):
    """并发度 >1 时，总耗时应明显短于串行（每章固定 0.2s）。"""
    dl = NovelDownloader(output_dir=str(tmp_path))
    chapters = _chapters(4)

    async def slow_fetcher(url: str) -> str:
        import asyncio

        await asyncio.sleep(0.2)
        return "正文"

    started = time.time()
    result = await dl.download_chapters(
        book_title="测试书",
        author="某作者",
        chapters=chapters,
        content_fetcher=slow_fetcher,
        concurrency=4,
        delay=0,
    )
    elapsed = time.time() - started

    assert result["success_count"] == 4
    # 串行需要 ≥0.8s；4 并发应在 0.5s 内完成
    assert elapsed < 0.5, f"未并发执行，耗时 {elapsed:.2f}s"
