"""Read-only diagnostic: list non-terminal task ledger rows."""

import asyncio
import json

from sqlalchemy import select

from app.db.database import get_async_session
from app.db.models.task import (
    Model3DGenerationTask,
    ProjectTaskRecord,
    VideoGenerationTask,
)


ACTIVE = ("pending", "running", "processing", "queued")


async def main() -> None:
    async with get_async_session() as session:
        for model, label in (
            (VideoGenerationTask, "video"),
            (Model3DGenerationTask, "model3d"),
            (ProjectTaskRecord, "project"),
        ):
            rows = (
                await session.execute(select(model).where(model.status.in_(ACTIVE)))
            ).scalars().all()
            print(f"== {label}: {len(rows)}")
            for row in rows:
                print(json.dumps({
                    "task_id": row.task_id,
                    "status": row.status,
                    "provider": getattr(row, "provider", None),
                    "model": getattr(row, "model", None),
                    "progress": row.progress,
                    "progress_message": row.progress_message,
                    "created_at": row.created_at,
                    "updated_at": getattr(row, "updated_at", None),
                    "completed_at": getattr(row, "completed_at", None),
                    "owner_user_id": getattr(row, "owner_user_id", None),
                    "error": getattr(row, "error", None),
                    "result_json": getattr(row, "result_json", None),
                }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
