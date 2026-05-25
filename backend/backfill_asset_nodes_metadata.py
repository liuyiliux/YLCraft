#!/usr/bin/env python3
"""
补齐 asset_nodes.metadata_json 脚本

问题：混合搜索查 asset_nodes 表，但旧的 B站视频在 asset_nodes 中 metadata_json 为空，
     导致点击详情无数据。

解决：从 assets 表读取对应字段，同步到 asset_nodes.metadata_json。
     两个表共享同一个 UUID id。

用法：
    cd backend
    python backfill_asset_nodes_metadata.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")


async def backfill():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    import os
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://ylcraft:ylcraft_dev@localhost:5432/ylcraft",
    )

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. 查询需要补齐的 asset_nodes（metadata_json 为空）
        result = await session.execute(
            text("""
                SELECT an.id, an.name, an.asset_type
                FROM asset_nodes an
                WHERE an.metadata_json IS NULL OR an.metadata_json = '{}'::jsonb
            """)
        )
        rows = result.fetchall()
        total = len(rows)
        logger.info(f"找到 {total} 个 metadata_json 为空的 asset_nodes")

        updated = 0
        for row in rows:
            node_id = row[0]

            # 2. 从 assets 表读取对应数据
            asset_result = await session.execute(
                text("""
                    SELECT platform, title, author, source_url, source_type,
                           width, height, duration, file_size,
                           cover_url, status, tags
                    FROM assets
                    WHERE id = :node_id
                """),
                {"node_id": node_id},
            )
            asset_row = asset_result.fetchone()

            if not asset_row:
                logger.debug(f"  跳过 {node_id}: assets 中无对应记录")
                continue

            (platform, title, author, source_url, source_type,
             width, height, duration, file_size,
             cover_url, status, tags) = asset_row

            # 3. 构建 metadata_json
            metadata = {}

            if platform:
                metadata["platform"] = platform

            if source_url:
                metadata["source_url"] = source_url

            if source_type:
                metadata["source_type"] = source_type
            elif platform:
                metadata["source_type"] = "parse"
            else:
                metadata["source_type"] = "upload"

            if author:
                metadata["author"] = author

            if width:
                metadata["width"] = width
            if height:
                metadata["height"] = height
            if duration:
                metadata["duration"] = duration
            if file_size:
                metadata["file_size"] = file_size

            if status:
                metadata["status"] = status

            if width and height:
                metadata["resolution"] = f"{width}x{height}"

            if cover_url:
                metadata["cover_url"] = cover_url

            # 解析 tags
            if tags:
                try:
                    parsed_tags = json.loads(tags)
                    if isinstance(parsed_tags, list):
                        metadata["tags"] = parsed_tags
                except (json.JSONDecodeError, TypeError):
                    pass

            # 4. 更新 asset_nodes
            await session.execute(
                text("""
                    UPDATE asset_nodes
                    SET metadata_json = :meta::jsonb,
                        thumbnail_url = COALESCE(NULLIF(thumbnail_url, ''), :cover_url)
                    WHERE id = :node_id
                """),
                {
                    "meta": json.dumps(metadata, ensure_ascii=False),
                    "cover_url": cover_url or "",
                    "node_id": node_id,
                },
            )
            updated += 1

        await session.commit()
        logger.info(f"补齐完成: {updated}/{total} 条 record 已更新")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill())
