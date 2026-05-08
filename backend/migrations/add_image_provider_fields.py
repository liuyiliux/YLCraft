"""
数据库迁移脚本：为 ai_connectors 表添加图像/视频生成支持字段
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os

# 从环境变量获取数据库 URL
DATABASE_URL = "sqlite:///F:/PycharmProjects/YLCraft/backend/data/ylcraft.db"

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)


def migrate():
    """执行迁移"""
    session = Session()
    try:
        print("开始迁移 ai_connectors 表...")

        # 检查列是否已存在
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("ai_connectors")]

        # 添加新列
        if "provider_type" not in columns:
            print("  - 添加 provider_type 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN provider_type VARCHAR(20) DEFAULT 'llm'"
            ))

        if "request_template" not in columns:
            print("  - 添加 request_template 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN request_template TEXT"
            ))

        if "response_config" not in columns:
            print("  - 添加 response_config 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN response_config TEXT"
            ))

        if "parameter_transforms" not in columns:
            print("  - 添加 parameter_transforms 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN parameter_transforms TEXT"
            ))

        if "supported_sizes" not in columns:
            print("  - 添加 supported_sizes 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN supported_sizes TEXT"
            ))

        if "default_params" not in columns:
            print("  - 添加 default_params 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN default_params TEXT"
            ))

        if "support_reference_image" not in columns:
            print("  - 添加 support_reference_image 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN support_reference_image BOOLEAN DEFAULT 0"
            ))

        if "support_multiple_reference_images" not in columns:
            print("  - 添加 support_multiple_reference_images 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN support_multiple_reference_images BOOLEAN DEFAULT 0"
            ))

        if "reference_image_field" not in columns:
            print("  - 添加 reference_image_field 列...")
            session.execute(text(
                "ALTER TABLE ai_connectors ADD COLUMN reference_image_field VARCHAR(50) DEFAULT 'image'"
            ))

        session.commit()
        print("✅ 迁移完成！")

        # 显示当前表结构
        print("\n当前 ai_connectors 表结构：")
        result = session.execute(text("PRAGMA table_info(ai_connectors)"))
        for row in result:
            print(f"  - {row[1]} ({row[2]})")

    except Exception as e:
        session.rollback()
        print(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
