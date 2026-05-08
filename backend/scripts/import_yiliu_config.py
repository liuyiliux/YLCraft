"""
将 yiliu 项目的 YAML 配置导入到 YLCraft 数据库

使用方法:
    python import_yiliu_config.py
"""

import sys
import os
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

# 添加 YLCraft 后端到 Python 路径
YLCMRAFT_BACKEND = r"F:\PycharmProjects\YLCraft\backend"
sys.path.insert(0, YLCMRAFT_BACKEND)

from sqlmodel import SQLModel, Session, create_engine
from app.db.models.ai_connector import (
    AIConnector,
    AIProvider,
    AIProviderType,
    AIModelTier
)


# =============================================================================
# 配置路径
# =============================================================================
YILIU_CONFIG_DIR = r"F:\workspace\图文\yiliu\config"
IMAGE_PROVIDERS_YAML = os.path.join(YILIU_CONFIG_DIR, "image_providers.yaml")
TEXT_PROVIDERS_YAML = os.path.join(YILIU_CONFIG_DIR, "text_providers.yaml")

# YLCraft 数据库
DATABASE_URL = "sqlite+aiosqlite:///F:/PycharmProjects/YLCraft/backend/data/ylcraft.db"
engine = create_engine(DATABASE_URL.replace("sqlite+aiosqlite:///", "sqlite:///"))


# =============================================================================
# 工具函数
# =============================================================================

def load_yaml(file_path: str) -> dict:
    """加载 YAML 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def map_provider_type(yiliu_type: str) -> AIProviderType:
    """映射 yiliu 的 type 到 AIProviderType"""
    mapping = {
        'openai': AIProviderType.llm,  # 需要根据实际功能判断
        'siliconflow': AIProviderType.llm,
        'generic': AIProviderType.llm,
    }
    return mapping.get(yiliu_type, AIProviderType.llm)


def map_provider(yiliu_provider: dict, provider_name: str) -> AIProvider:
    """映射 yiliu 的提供商到 AIProvider 枚举"""
    # 尝试从配置中识别提供商
    base_url = yiliu_provider.get('base_url', '').lower()
    model = yiliu_provider.get('model', '').lower()
    
    if 'openai' in base_url or 'openai' in model:
        return AIProvider.openai
    elif 'siliconflow' in base_url or 'siliconflow' in model:
        return AIProvider.qwen  # SiliconFlow 主要提供 Qwen 模型
    elif 'dashscope' in base_url or 'aliyun' in base_url:
        return AIProvider.qwen  # 百炼是阿里云
    elif 'anthropic' in base_url:
        return AIProvider.anthropic
    elif 'zhipu' in base_url or 'glm' in model:
        return AIProvider.ZHIPU
    elif 'deepseek' in model:
        return AIProvider.DEEPSEEK
    else:
        return AIProvider.openai  # 默认


def parse_size_string(size_str) -> str:
    """解析尺寸字符串，统一格式为 '1024x1024'"""
    if isinstance(size_str, str):
        # 替换 * 为 x
        return size_str.replace('*', 'x')
    return str(size_str)


def transform_image_provider(name: str, config: dict) -> AIConnector:
    """将 yiliu 图像提供商配置转换为 AIConnector"""
    
    # 提取配置
    api_key = config.get('api_key', '')
    base_url = config.get('base_url', '')
    model = config.get('model', config.get('image_model', ''))
    is_active = config.get('enabled', True)
    
    # 请求模板
    request_template = ''
    request_config = config.get('request_config', {})
    if request_config and request_config.get('template'):
        request_template = request_config.get('template', '')
    
    # 响应配置
    response_config = {}
    resp_cfg = config.get('response_config', {})
    if resp_cfg:
        response_config = {
            'images_path': resp_cfg.get('images_path', ''),
            'error_path': resp_cfg.get('error_path', ''),
            'usage_path': resp_cfg.get('usage_path', ''),
            'response_format': resp_cfg.get('response_format', 'url')
        }
    
    # 参数转换
    parameter_transforms = {}
    if request_config and request_config.get('parameter_transforms'):
        parameter_transforms = request_config.get('parameter_transforms', {})
    
    # 默认参数
    defaults = request_config.get('defaults', {}) if request_config else {}
    default_params = {
        'n': defaults.get('n', 1),
        'quality': defaults.get('quality', 'standard'),
        'watermark': defaults.get('watermark', False),
        'prompt_extend': defaults.get('prompt_extend', False)
    }
    
    # 支持的尺寸
    supported_sizes = []
    sizes = config.get('supported_sizes', [])
    for size in sizes:
        supported_sizes.append(parse_size_string(size))
    
    # 参考图支持
    support_ref = config.get('support_reference_image', False)
    support_multi_ref = config.get('support_multiple_reference_images', False)
    ref_field = config.get('reference_image_field', 'image')
    
    # 创建 AIConnector
    connector = AIConnector(
        id=str(uuid4()),
        provider=map_provider(config, name),
        provider_type=AIProviderType.image,  # 图像生成
        name=config.get('name', name),
        api_key=api_key,
        base_url=base_url,
        default_model=model,
        available_models=json.dumps([model] if model else []),
        is_active=is_active,
        is_default=False,
        priority=0,
        description=f"从 yiliu 导入: {name}",
        
        # 图像生成专用配置
        request_template=request_template if request_template else None,
        response_config=json.dumps(response_config) if response_config else None,
        parameter_transforms=json.dumps(parameter_transforms) if parameter_transforms else None,
        supported_sizes=json.dumps(supported_sizes) if supported_sizes else None,
        default_params=json.dumps(default_params),
        support_reference_image=support_ref,
        support_multiple_reference_images=support_multi_ref,
        reference_image_field=ref_field,
        
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    return connector


def transform_text_provider(name: str, config: dict) -> AIConnector:
    """将 yiliu 文本提供商配置转换为 AIConnector"""
    
    # 提取配置
    api_key = config.get('api_key', '')
    base_url = config.get('base_url', '')
    model = config.get('model', '')
    is_active = config.get('enabled', True)
    max_tokens = config.get('max_output_tokens', 4096)
    
    # 创建 AIConnector
    connector = AIConnector(
        id=str(uuid4()),
        provider=map_provider(config, name),
        provider_type=AIProviderType.llm,  # 文本生成
        name=config.get('name', name),
        api_key=api_key,
        base_url=base_url,
        default_model=model,
        available_models=json.dumps([model] if model else []),
        max_tokens=max_tokens,
        temperature=0.7,
        is_active=is_active,
        is_default=False,
        priority=0,
        description=f"从 yiliu 导入: {name}",
        
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    return connector


def import_image_providers(session: Session) -> int:
    """导入图像生成提供商"""
    print("\n📥 导入图像生成提供商...")
    
    if not os.path.exists(IMAGE_PROVIDERS_YAML):
        print(f"  ⚠️  文件不存在: {IMAGE_PROVIDERS_YAML}")
        return 0
    
    data = load_yaml(IMAGE_PROVIDERS_YAML)
    providers = data.get('providers', {})
    
    count = 0
    for name, config in providers.items():
        print(f"  🔄 处理: {name}")
        
        try:
            connector = transform_image_provider(name, config)
            
            # 检查是否已存在（按 name 和 base_url 检查）
            existing = session.query(AIConnector).filter(
                AIConnector.name == connector.name,
                AIConnector.base_url == connector.base_url
            ).first()
            
            if existing:
                print(f"    ⚠️  已存在，跳过: {connector.name}")
                continue
            
            session.add(connector)
            count += 1
            print(f"    ✅ 已添加: {connector.name} (ID: {connector.id[:8]}...)")
            
        except Exception as e:
            print(f"    ❌ 错误: {str(e)}")
    
    session.commit()
    print(f"\n  ✅ 成功导入 {count} 个图像生成提供商")
    return count


def import_text_providers(session: Session) -> int:
    """导入文本生成提供商"""
    print("\n📥 导入文本生成提供商...")
    
    if not os.path.exists(TEXT_PROVIDERS_YAML):
        print(f"  ⚠️  文件不存在: {TEXT_PROVIDERS_YAML}")
        return 0
    
    data = load_yaml(TEXT_PROVIDERS_YAML)
    providers = data.get('providers', {})
    
    count = 0
    for name, config in providers.items():
        print(f"  🔄 处理: {name}")
        
        try:
            connector = transform_text_provider(name, config)
            
            # 检查是否已存在
            existing = session.query(AIConnector).filter(
                AIConnector.name == connector.name,
                AIConnector.base_url == connector.base_url
            ).first()
            
            if existing:
                print(f"    ⚠️  已存在，跳过: {connector.name}")
                continue
            
            session.add(connector)
            count += 1
            print(f"    ✅ 已添加: {connector.name} (ID: {connector.id[:8]}...)")
            
        except Exception as e:
            print(f"    ❌ 错误: {str(e)}")
    
    session.commit()
    print(f"\n  ✅ 成功导入 {count} 个文本生成提供商")
    return count


def list_existing_connectors(session: Session):
    """列出已有的连接器"""
    print("\n📋 已有的 AI 连接器:")
    connectors = session.query(AIConnector).all()
    
    if not connectors:
        print("  (无)")
        return
    
    for conn in connectors:
        print(f"  - {conn.name} ({conn.provider_type}) - {'✅ 启用' if conn.is_active else '❌ 禁用'}")


# =============================================================================
# 主函数
# =============================================================================

def main():
    print("=" * 80)
    print("🚀 YLCraft - 导入 yiliu 配置")
    print("=" * 80)
    
    # 检查 YAML 文件
    print("\n📁 检查配置文件...")
    if not os.path.exists(IMAGE_PROVIDERS_YAML):
        print(f"  ❌ 图像配置不存在: {IMAGE_PROVIDERS_YAML}")
        return
    if not os.path.exists(TEXT_PROVIDERS_YAML):
        print(f"  ❌ 文本配置不存在: {TEXT_PROVIDERS_YAML}")
        return
    print("  ✅ 配置文件存在")
    
    # 连接数据库
    print(f"\n💾 连接数据库...")
    print(f"  URL: {DATABASE_URL}")
    
    with Session(engine) as session:
        # 列出已有的连接器
        list_existing_connectors(session)
        
        # 导入图像生成提供商
        image_count = import_image_providers(session)
        
        # 导入文本生成提供商
        text_count = import_text_providers(session)
        
        # 最终统计
        print("\n" + "=" * 80)
        print("📊 导入完成")
        print("=" * 80)
        print(f"  图像生成提供商: {image_count} 个")
        print(f"  文本生成提供商: {text_count} 个")
        print(f"  总计: {image_count + text_count} 个")
        
        # 列出所有连接器
        list_existing_connectors(session)
        
        print("\n✅ 全部完成！")


if __name__ == "__main__":
    main()
