"""
迁移脚本：统一凭证架构

将旧的三表凭证数据合并到 PlatformConnection：
  - platform_cookies → PlatformConnection.cookie_content
  - social_media_connectors → PlatformConnection.account_* 字段

注意：此脚本应在旧表被删除前运行，且可以安全地重复运行（幂等）。
"""

import json
import logging
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ylcraft.migration")


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    """检查表中是否存在指定列"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def _table_exists(cursor, table_name: str) -> bool:
    """检查表是否存在"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def migrate():
    """执行统一凭证迁移"""
    from app.db.database import sync_engine

    with sync_engine.connect() as conn:
        cursor = conn.connection.cursor()

        # =========================================================================
        # Step 1: 确保 platform_connections 表有新字段
        # =========================================================================
        logger.info("Step 1: 检查并添加 PlatformConnection 新字段...")

        new_columns = [
            ("acquisition_method", "VARCHAR(20) DEFAULT 'manual'"),
            ("account_id", "VARCHAR(255)"),
            ("account_name", "VARCHAR(255)"),
            ("account_avatar", "TEXT"),
            ("account_url", "TEXT"),
            ("cookie_content", "TEXT"),
            ("domains", "VARCHAR(1000)"),
            ("test_url", "VARCHAR(500)"),
        ]

        for col_name, col_type in new_columns:
            if not _column_exists(cursor, "platform_connections", col_name):
                try:
                    cursor.execute(
                        f"ALTER TABLE platform_connections ADD COLUMN {col_name} {col_type}"
                    )
                    conn.commit()
                    logger.info(f"  ✅ 添加字段: {col_name}")
                except Exception as e:
                    logger.warning(f"  ⚠️ 添加字段 {col_name} 失败（可能已存在）: {e}")
            else:
                logger.info(f"  ⏭️ 字段已存在: {col_name}")

        # =========================================================================
        # Step 2: 迁移 platform_cookies 数据
        # =========================================================================
        if _table_exists(cursor, "platform_cookies"):
            logger.info("Step 2: 迁移 platform_cookies 数据...")
            cursor.execute("SELECT id, platform, cookie_content, created_at FROM platform_cookies")
            rows = cursor.fetchall()
            migrated = 0
            skipped = 0

            for row in rows:
                old_id, platform, cookie_content, created_at = row
                if not cookie_content:
                    skipped += 1
                    continue

                # 检查是否已有同平台同类型的连接
                cursor.execute(
                    "SELECT id FROM platform_connections WHERE platform = ? AND auth_type = 'cookie'",
                    (platform,),
                )
                existing = cursor.fetchone()

                if existing:
                    # 更新现有连接
                    cursor.execute(
                        "UPDATE platform_connections SET cookie_content = ?, acquisition_method = 'manual' WHERE id = ?",
                        (cookie_content, existing[0]),
                    )
                    logger.info(f"  🔄 更新已有连接: {platform} → {existing[0]}")
                else:
                    # 创建新连接
                    new_id = str(uuid.uuid4())
                    cursor.execute(
                        """INSERT INTO platform_connections 
                           (id, platform, name, auth_type, status, credentials, cookie_content, acquisition_method, created_at, updated_at)
                           VALUES (?, ?, ?, 'cookie', 'unknown', '{}', ?, 'manual', ?, ?)""",
                        (new_id, platform, f"{platform} Cookie", cookie_content, created_at, created_at),
                    )
                    logger.info(f"  ➕ 创建新连接: {platform} → {new_id}")

                migrated += 1

            conn.commit()
            logger.info(f"  ✅ 迁移完成: {migrated} 条记录，跳过 {skipped} 条空记录")
        else:
            logger.info("Step 2: ⏭️ platform_cookies 表不存在，跳过")

        # =========================================================================
        # Step 3: 迁移 social_media_connectors 数据
        # =========================================================================
        if _table_exists(cursor, "social_media_connectors"):
            logger.info("Step 3: 迁移 social_media_connectors 数据...")
            cursor.execute("SELECT id, platform, name, credentials, account_id, account_name, created_at FROM social_media_connectors")
            rows = cursor.fetchall()
            migrated = 0

            for row in rows:
                old_id, platform, name, credentials, account_id, account_name, created_at = row

                # 检查是否已有同平台连接
                cursor.execute(
                    "SELECT id, credentials FROM platform_connections WHERE platform = ?",
                    (platform,),
                )
                existing = cursor.fetchone()

                if existing:
                    # 更新现有连接的 account 信息
                    cursor.execute(
                        "UPDATE platform_connections SET account_id = ?, account_name = ? WHERE id = ?",
                        (account_id, account_name, existing[0]),
                    )
                    # 合并 credentials
                    if credentials:
                        old_creds = json.loads(existing[1]) if existing[1] else {}
                        new_creds = json.loads(credentials) if isinstance(credentials, str) else credentials
                        merged = {**old_creds, **new_creds, "social_media_merged": True}
                        cursor.execute(
                            "UPDATE platform_connections SET credentials = ? WHERE id = ?",
                            (json.dumps(merged, ensure_ascii=False), existing[0]),
                        )
                    logger.info(f"  🔄 更新已有连接: {platform} → {existing[0]}")
                else:
                    # 创建新连接
                    new_id = str(uuid.uuid4())
                    cursor.execute(
                        """INSERT INTO platform_connections 
                           (id, platform, name, auth_type, status, credentials, account_id, account_name, created_at, updated_at)
                           VALUES (?, ?, ?, 'cookie', 'unknown', ?, ?, ?, ?, ?)""",
                        (new_id, platform, name or f"{platform} Social", credentials or "{}", account_id, account_name, created_at, created_at),
                    )
                    logger.info(f"  ➕ 创建新连接: {platform} → {new_id}")

                migrated += 1

            conn.commit()
            logger.info(f"  ✅ 迁移完成: {migrated} 条记录")
        else:
            logger.info("Step 3: ⏭️ social_media_connectors 表不存在，跳过")

        # =========================================================================
        # Step 4: 数据校验
        # =========================================================================
        logger.info("Step 4: 数据校验...")
        cursor.execute("SELECT COUNT(*) FROM platform_connections")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM platform_connections WHERE cookie_content IS NOT NULL AND cookie_content != ''")
        with_cookie = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM platform_connections WHERE account_name IS NOT NULL AND account_name != ''")
        with_account = cursor.fetchone()[0]

        logger.info(f"  PlatformConnection 总数: {total}")
        logger.info(f"  有 Cookie 内容的: {with_cookie}")
        logger.info(f"  有账号信息的: {with_account}")

        logger.info("✅ 迁移脚本执行完毕！")


if __name__ == "__main__":
    print("=" * 60)
    print("YLCraft 统一凭证迁移脚本")
    print("=" * 60)
    migrate()
    print("\n迁移完成！可以安全删除旧表。")
