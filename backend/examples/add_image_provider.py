"""
添加图像生成 Provider 到数据库的示例脚本
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.models.ai_connector import AIConnector, AIProvider, AIProviderType


def add_gpt_image2():
    """添加 GPT-Image2 (DALL-E 3) 到数据库"""
    session = SessionLocal()
    try:
        # 检查是否已存在
        existing = session.query(AIConnector).filter(
            AIConnector.name == "GPT-Image2"
        ).first()
        
        if existing:
            print(f"Provider 已存在: {existing.name}")
            return
        
        # 创建新 Provider
        connector = AIConnector(
            id="gpt-image2-001",  # 唯一 ID
            provider=AIProvider.openai,
            provider_type=AIProviderType.image,
            name="GPT-Image2 (DALL-E 3)",
            api_key="your-openai-api-key-here",  # 或从环境变量读取
            base_url="https://api.openai.com/v1/images/generations",
            default_model="dall-e-3",
            is_active=True,
            is_default=False,  # 设为 True 让它成为默认图像生成 Provider
            priority=1,
            description="OpenAI DALL-E 3 图像生成",
            
            # GenericImageBackend 所需配置
            request_template="""
{
    "model": "{{ default_model }}",
    "prompt": "{{ prompt }}",
    "size": "{{ size | default('1024x1024') }}",
    "n": {{ n | default(1) }},
    "quality": "{{ quality | default('standard') }}"
}
""",
            
            response_config='{"images_path": "$.data[*].url", "error_path": "$.error.message"}',
            
            default_params='{"n": 1, "quality": "standard", "size": "1024x1024"}',
            
            supported_sizes='["1024x1024", "1792x1024", "1024x1792"]',
        )
        
        session.add(connector)
        session.commit()
        print(f"✅ 已添加 Provider: {connector.name}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ 添加失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


def add_minimax_image():
    """添加 MiniMax Seedance 2.0 到数据库（使用 GenericImageBackend）"""
    session = SessionLocal()
    try:
        existing = session.query(AIConnector).filter(
            AIConnector.name == "MiniMax-Seedance"
        ).first()
        
        if existing:
            print(f"Provider 已存在: {existing.name}")
            return
        
        connector = AIConnector(
            id="minimax-image-001",
            provider=AIProvider.MINIMAX,
            provider_type=AIProviderType.image,
            name="MiniMax Seedance 2.0",
            api_key="your-minimax-api-key-here",
            base_url="https://api.minimax.chat/v1/images/generations",
            default_model="seedance-2.0",
            is_active=True,
            is_default=False,
            priority=2,
            description="MiniMax Seedance 2.0 图像生成",
            
            request_template="""
{
    "model": "{{ default_model }}",
    "prompt": "{{ prompt }}",
    "negative_prompt": "{{ negative_prompt | default('') }}",
    "size": "{{ size | default('1024x1024') }}"
}
""",
            
            response_config='{"images_path": "$.data[*].url", "error_path": "$.error.message"}',
            
            default_params='{"size": "1024x1024"}',
        )
        
        session.add(connector)
        session.commit()
        print(f"✅ 已添加 Provider: {connector.name}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ 添加失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    print("添加图像生成 Provider 到数据库...")
    print("=" * 50)
    
    # 添加 GPT-Image2
    add_gpt_image2()
    
    # 添加 MiniMax
    # add_minimax_image()
    
    print("\n完成！现在重启后端服务以加载新的 Provider。")
    print("重启命令: cd backend && uvicorn app.main:app --reload --port 8000")
