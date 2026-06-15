"""
EPUB 电子书业务服务
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .epub_builder import EpubBuilder

logger = logging.getLogger("ylcraft.ebook.service")


class EbookService:
    """
    EPUB 电子书生成服务

    管理生成任务，调用 EpubBuilder 构建 EPUB。
    """

    def __init__(self):
        self._tasks: dict[str, dict] = {}

    async def create_task(
        self,
        title: str,
        folder_path: str,
        author: str = "YLCraft",
        cover_path: str = "",
        output_dir: str = "",
    ) -> dict:
        """
        创建 EPUB 生成任务

        Returns:
            { task_id, status, title, chapter_count }
        """
        task_id = str(uuid.uuid4())

        builder = EpubBuilder(title=title, author=author)
        chapter_count = builder.collect_from_folder(folder_path)

        if chapter_count == 0:
            return {
                "task_id": task_id,
                "status": "failed",
                "title": title,
                "chapter_count": 0,
                "error": "文件夹中没有找到可用的 Markdown/HTML 文件",
            }

        if cover_path:
            builder.set_cover(cover_path)

        # 生成 EPUB（同步方法，在 executor 中运行）
        if not output_dir:
            output_dir = str(Path(folder_path).parent)

        try:
            import asyncio
            loop = asyncio.get_running_loop()
            epub_path = await loop.run_in_executor(None, builder.build, output_dir)
        except Exception as e:
            logger.error(f"[EbookService] 生成失败: {e}")
            return {
                "task_id": task_id,
                "status": "failed",
                "title": title,
                "chapter_count": chapter_count,
                "error": str(e),
            }

        file_size = os.path.getsize(epub_path) if os.path.exists(epub_path) else 0

        self._tasks[task_id] = {
            "task_id": task_id,
            "status": "done",
            "title": title,
            "chapter_count": chapter_count,
            "file_path": epub_path,
            "file_size": file_size,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }

        return {
            "task_id": task_id,
            "status": "done",
            "title": title,
            "chapter_count": chapter_count,
            "file_path": epub_path,
            "file_size": file_size,
        }

    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        """列出所有任务"""
        return sorted(
            self._tasks.values(),
            key=lambda t: t.get("created_at", ""),
            reverse=True,
        )


# ── 全局单例 ──────────────────────────────────────────────────

_ebook_service: Optional[EbookService] = None


def get_ebook_service() -> EbookService:
    global _ebook_service
    if _ebook_service is None:
        _ebook_service = EbookService()
    return _ebook_service
