"""测试标签API，复现错误"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

from app.db.database import get_async_session
from app.services.tag.service import TagService
from sqlmodel import select
from app.db.models.asset_hub import Tag


async def test_tag_query():
    """测试标签查询"""
    print("=== 测试标签查询 ===")
    
    try:
        # 先测试直接的SQL查询
        async with get_async_session() as session:
            print("1. 测试简单的Tag查询...")
            # 简单查询
            query = select(Tag)
            result = await session.execute(query)
            tags = list(result.scalars().all())
            print(f"   查询成功，找到 {len(tags)} 个标签")
            
            print("\n2. 测试带条件的查询...")
            # 测试带条件的查询
            query = select(Tag).order_by(Tag.asset_count.desc())
            result = await session.execute(query)
            tags = list(result.scalars().all())
            print(f"   查询成功，找到 {len(tags)} 个标签")
            
            print("\n3. 测试TagService.search_tags...")
            # 测试service方法
            service = TagService(session)
            tags = await service.search_tags()
            print(f"   service.search_tags 成功，返回 {len(tags)} 个标签")
            
            print("\n=== 所有测试通过 ===")
            
    except Exception as e:
        print(f"\n=== 错误发生 ===")
        print(f"类型: {type(e).__name__}")
        print(f"消息: {str(e)}")
        import traceback
        print(f"\n堆栈跟踪:\n{traceback.format_exc()}")


if __name__ == "__main__":
    asyncio.run(test_tag_query())

