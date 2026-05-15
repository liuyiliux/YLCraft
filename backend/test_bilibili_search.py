"""
测试 B站搜索功能
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.services.platforms.bilibili.client import BilibiliClient
from app.services.platforms.types import ClientConfig, ClientMode, SearchParams, SearchType


async def test_bilibili_search():
    """测试 B站搜索（API 模式）"""
    print("=" * 60)
    print("测试 1：B站搜索视频（API 模式）")
    print("=" * 60)
    
    config = ClientConfig(
        platform='bili',
        mode=ClientMode.API,
        cookie='',  # B站搜索不需要 Cookie
    )
    
    client = BilibiliClient(config)
    
    async with client:
        # 搜索视频
        results = await client.search_videos('鬼灭之刃', max_results=5)
        
        print(f"\n找到 {len(results)} 个结果：\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r.title}")
            print(f"   UP主：{r.author}")
            print(f"   播放：{r.views}")
            print(f"   URL: {r.url}\n")


async def test_bilibili_search_with_wrapper():
    """测试通过 wrapper 调用"""
    print("=" * 60)
    print("测试 2：通过 search_platform() 调用")
    print("=" * 60)
    
    from app.services.platforms import search
    
    results = await search(
        platform='bili',
        keyword='鬼灭之刃',
        mode='api',
        max_results=5,
    )
    
    print(f"\n找到 {len(results)} 个结果：\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r.get('title', '')}")
        print(f"   UP主：{r.get('author', '')}")
        print(f"   播放：{r.get('views', 0)}")
        print(f"   URL: {r.get('url', '')}\n")


async def test_bilibili_user_search():
    """测试搜索用户"""
    print("=" * 60)
    print("测试 3：B站搜索用户")
    print("=" * 60)
    
    config = ClientConfig(
        platform='bili',
        mode=ClientMode.API,
    )
    
    client = BilibiliClient(config)
    
    async with client:
        results = await client.search_users('鬼灭之刃', max_results=3)
        
        print(f"\n找到 {len(results)} 个用户：\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r.title}")
            print(f"   URL: {r.url}\n")


async def main():
    """运行所有测试"""
    try:
        await test_bilibili_search()
        await test_bilibili_search_with_wrapper()
        await test_bilibili_user_search()
        
        print("=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
