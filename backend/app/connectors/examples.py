"""
YLCraft — 连接器使用示例

展示如何使用新的平台连接器架构：
1. 从数据库获取凭证
2. 创建连接器实例
3. 执行各种操作
"""

from __future__ import annotations

import asyncio
from typing import Optional

# 导入数据库模型
from app.db.database import AsyncSessionLocal
from app.db.models import AIConnector as AIConnectorModel
from app.db.models.platform_connection import PlatformConnection

# 导入连接器
from app.connectors.registry import get_social_connector, get_ai_connector
from app.connectors.base import PostContent, PostResult, ChatRequest, ChatResponse
from app.connectors.base import ContentType, MediaAttachment, MediaFormat


# =============================================================================
# 示例 1: 使用 AI 连接器
# =============================================================================

async def example_ai_chat():
    """AI 对话示例"""
    async with AsyncSessionLocal() as session:
        # 从数据库获取 OpenAI 连接
        from sqlmodel import select
        from app.db.models import AIProvider

        stmt = select(AIConnectorModel).where(
            AIConnectorModel.provider == AIProvider.OPENAI,
            AIConnectorModel.is_active == True,
        )
        model = await session.execute(stmt).scalars()
        connector_model = model.first()

        if not connector_model:
            print("No OpenAI connector found")
            return

        # 创建连接器实例
        connector = get_ai_connector(
            provider_id="openai",
            api_key=connector_model.api_key,
            config={"organization_id": connector_model.organization_id} if connector_model.organization_id else None,
        )

        # 初始化
        if not await connector.initialize():
            print("Failed to initialize connector")
            return

        try:
            # 对话请求
            request = ChatRequest(
                messages=[
                    {"role": "system", "content": "你是一个有帮助的助手。"},
                    {"role": "user", "content": "解释一下什么是 AI 连接器。"},
                ],
                model="gpt-4o",
                temperature=0.7,
                max_tokens=500,
            )

            response: ChatResponse = await connector.chat(request)

            if response.success:
                print(f"Response: {response.content}")
                print(f"Cost: ${response.cost:.4f}")
                print(f"Latency: {response.latency_ms}ms")
            else:
                print(f"Error: {response.error}")

        finally:
            await connector.close()


# =============================================================================
# 示例 2: 使用社交媒体连接器
# =============================================================================

async def example_social_publish():
    """社交媒体发布示例"""
    async with AsyncSessionLocal() as session:
        # 从数据库获取小红书连接
        from sqlmodel import select
        from app.db.models import SocialMediaPlatform

        stmt = select(SocialConnectorModel).where(
            SocialConnectorModel.platform == SocialMediaPlatform.XHS,
        )
        model = await session.execute(stmt).scalars()
        connector_model = model.first()

        if not connector_model:
            print("No XHS connector found")
            return

        # 创建连接器实例
        credentials = connector_model.get_credentials()
        connector = get_social_connector(platform_id="xhs", credentials=credentials)

        # 初始化
        if not await connector.initialize():
            print("Failed to initialize connector")
            return

        try:
            # 获取账号信息
            account_info = await connector.get_account_info()
            print(f"Connected as: {account_info.display_name}")

            # 发布图文笔记
            content = PostContent(
                title="AI 工具推荐 | 提高效率 10 倍",
                body="今天给大家推荐几款我一直在用的 AI 工具...",
                content_type=ContentType.IMAGE,
                tags=["AI", "效率工具", "推荐"],
                media=[
                    MediaAttachment(
                        file_path="/path/to/screenshot.jpg",
                        media_type=MediaFormat.JPG,
                        caption="工具截图",
                    ),
                ],
            )

            result: PostResult = await connector.publish(content)

            if result.success:
                print(f"Published! URL: {result.post_url}")
            else:
                print(f"Failed: {result.error_message}")

        finally:
            await connector.close()


# =============================================================================
# 示例 3: 批量使用多个平台
# =============================================================================

async def example_multi_platform():
    """多平台发布示例"""
    platforms = ["xhs", "douyin", "weibo"]

    content = PostContent(
        title="多平台同步内容",
        body="这是一条同步发布到多个平台的内容...",
        content_type=ContentType.IMAGE,
    )

    results = {}

    for platform in platforms:
        async with AsyncSessionLocal() as session:
            try:
                # 获取连接
                from sqlmodel import select
                stmt = select(SocialConnectorModel).where(
                    SocialConnectorModel.platform == platform,
                )
                model = await session.execute(stmt).scalars()
                connector_model = model.first()

                if not connector_model:
                    results[platform] = {"success": False, "error": "No connector found"}
                    continue

                # 创建并使用连接器
                credentials = connector_model.get_credentials()
                connector = get_social_connector(platform, credentials)

                if not await connector.initialize():
                    results[platform] = {"success": False, "error": "Init failed"}
                    continue

                try:
                    result = await connector.publish(content)
                    results[platform] = {
                        "success": result.success,
                        "post_url": result.post_url,
                        "error": result.error_message,
                    }
                finally:
                    await connector.close()

            except Exception as e:
                results[platform] = {"success": False, "error": str(e)}

    # 汇总结果
    print("\n=== Multi-Platform Publishing Results ===")
    for platform, result in results.items():
        status = "OK" if result["success"] else "FAILED"
        print(f"{platform}: {status} - {result.get('post_url') or result.get('error')}")


# =============================================================================
# 主函数
# =============================================================================

async def main():
    """运行所有示例"""
    print("=== AI Chat Example ===")
    await example_ai_chat()

    print("\n=== Social Media Publish Example ===")
    await example_social_publish()

    print("\n=== Multi-Platform Example ===")
    await example_multi_platform()


if __name__ == "__main__":
    asyncio.run(main())
