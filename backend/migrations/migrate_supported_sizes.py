"""
迁移脚本：将 supported_sizes 从逗号分隔格式转换为 JSON 数组格式
"""

import json
from sqlmodel import select
from app.db.database import SessionLocal
from app.db.models.ai_connector import AIConnector


def migrate_supported_sizes():
    """迁移 supported_sizes 字段"""
    db = SessionLocal()
    try:
        # 查找所有 AI 连接器
        stmt = select(AIConnector)
        connectors = db.execute(stmt).scalars().all()

        migrated_count = 0
        for conn in connectors:
            if conn.supported_sizes and isinstance(conn.supported_sizes, str):
                # 检查是否是逗号分隔格式（而非 JSON 格式）
                sizes_value = conn.supported_sizes.strip()
                if sizes_value and not sizes_value.startswith('['):
                    # 转换为 JSON 数组
                    sizes_list = [s.strip() for s in sizes_value.split(',') if s.strip()]
                    conn.supported_sizes = json.dumps(sizes_list)
                    db.add(conn)
                    migrated_count += 1
                    print(f"  迁移: {conn.name} -> {conn.supported_sizes}")

        if migrated_count > 0:
            db.commit()
            print(f"\n成功迁移 {migrated_count} 条记录")
        else:
            print("\n没有需要迁移的记录")

    except Exception as e:
        db.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("开始迁移 supported_sizes 字段...")
    migrate_supported_sizes()
    print("迁移完成！")
