"""
将 yiliu 项目的 YAML 配置导入到 YLCraft 数据库
使用 SQLAlchemy Core 直接操作，避免 SQLModel 关系问题

使用方法:
    python import_yiliu_config_v2.py
"""

import sys
import os
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

# 添加 YLCraft 后端到 Python 路径
YLCMRAFT_BACKEND = r"F:\PycharmProjects\YLCraft\backend"
sys.path.insert(0, YLCMRAFT_BACKEND)

from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.orm import sessionmaker


# =============================================================================
# 配置路径
# =============================================================================
YILIU_CONFIG_DIR = r"F:\workspace\图文\yiliu\config"
IMAGE_PROVIDERS_YAML = os.path.join(YILIU_CONFIG_DIR, "image_providers.yaml")
TEXT_PROVIDERS_YAML = os.path.join(YILIU_CONFIG_DIR, "text_providers.yaml")

# YLCraft 数据库
DATABASE_URL = "sqlite:///F:/PycharmProjects/YLCraft/backend/data/ylcraft.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# 反射数据库表结构
metadata = MetaData()
metadata.reflect(bind=engine)
ai_connectors_table = metadata.tables['ai_connectors']


# =============================================================================
# 工具函数
# =============================================================================

def load_yaml(file_path: str) -> dict:
    """加载 YAML 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def parse_size_string(size_str) -> str:
    """解析尺寸字符串，统一格式为 '1024x1024'"""
    if isinstance(size_str, str):
        return size_str.replace('*', 'x')
    return str(size_str)


def map_provider_from_config(config: dict) -> str:
    """
    从配置中识别提供商类型，返回枚举值（小写）
    例如：'openai' -> 'openai', 'qwen' -> 'qwen'
    """
    base_url = config.get('base_url', '').lower()
    model = config.get('model', '').lower()
    
    # 映射规则
    if 'openai' in base_url or 'openai' in model:
        return 'openai'
    elif 'siliconflow' in base_url or 'siliconflow' in model or 'qwen' in model:
        return 'qwen'
    elif 'dashscope' in base_url or 'aliyun' in base_url:
        return 'qwen'
    elif 'anthropic' in base_url:
        return 'anthropic'
    elif 'zhipu' in base_url or 'glm' in model:
        return 'zhipu'
    elif 'deepseek' in model:
        return 'deepseek'
    else:
        return 'openai'  # 默认


def transform_image_provider(name: str, config: dict) -> dict:
    """将 yiliu 图像提供商配置转换为 AIConnector 字典"""
    
    api_key = config.get('api_key', '')
    base_url = config.get('base_url', '')
    model = config.get('model', config.get('image_model', ''))
    is_active = config.get('enabled', True)
    provider_type = 'image'
    
    # 请求模板
    request_template = None
    request_config = config.get('request_config', {})
    if request_config and isinstance(request_config, dict):
        request_template = request_config.get('template', '') or None
    
    # 响应配置
    response_config = {}
    resp_cfg = config.get('response_config', {})
    
    # 获取 images_path：优先使用 response_config.images_path，否则使用顶层的 image_jsonpath
    images_path = ''
    if resp_cfg and isinstance(resp_cfg, dict):
        images_path = resp_cfg.get('images_path', '')
    
    # 如果 images_path 为空，尝试使用顶层的 image_jsonpath
    if not images_path:
        images_path = config.get('image_jsonpath', '')
    
    if resp_cfg and isinstance(resp_cfg, dict):
        response_config = {
            'images_path': images_path,
            'error_path': resp_cfg.get('error_path', ''),
            'usage_path': resp_cfg.get('usage_path', ''),
            'response_format': resp_cfg.get('response_format', 'url')
        }
    elif images_path:
        # 如果没有 response_config，但有 image_jsonpath
        response_config = {
            'images_path': images_path,
            'error_path': '',
            'usage_path': '',
            'response_format': config.get('return_format', 'url')
        }
    
    # 参数转换
    parameter_transforms = None
    if request_config and isinstance(request_config, dict):
        transforms = request_config.get('parameter_transforms', {})
        if transforms:
            parameter_transforms = transforms
    
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
    if sizes and isinstance(sizes, list):
        for size in sizes:
            supported_sizes.append(parse_size_string(size))
    
    # 参考图支持
    support_ref = config.get('support_reference_image', False)
    support_multi_ref = config.get('support_multiple_reference_images', False)
    ref_field = config.get('reference_image_field', 'image')
    
    now = datetime.now(timezone.utc)
    
    return {
        'id': str(uuid4()),
        'provider': map_provider_from_config(config),
        'provider_type': provider_type,
        'name': config.get('name', name),
        'api_key': api_key,
        'base_url': base_url,
        'default_model': model,
        'available_models': json.dumps([model] if model else []),
        'is_active': is_active,
        'is_default': False,
        'priority': 0,
        'description': f"从 yiliu 导入: {name}",
        
        # 图像生成专用配置
        'request_template': request_template,
        'response_config': json.dumps(response_config) if response_config else None,
        'parameter_transforms': json.dumps(parameter_transforms) if parameter_transforms else None,
        'supported_sizes': json.dumps(supported_sizes) if supported_sizes else None,
        'default_params': json.dumps(default_params),
        'support_reference_image': support_ref,
        'support_multiple_reference_images': support_multi_ref,
        'reference_image_field': ref_field,
        
        'max_tokens': 4096,
        'temperature': 0.7,
        'usage_count': 0,
        'total_cost': 0.0,
        
        'created_at': now,
        'updated_at': now,
    }


def transform_text_provider(name: str, config: dict) -> dict:
    """将 yiliu 文本提供商配置转换为 AIConnector 字典"""
    
    api_key = config.get('api_key', '')
    base_url = config.get('base_url', '')
    model = config.get('model', '')
    is_active = config.get('enabled', True)
    max_tokens = config.get('max_output_tokens', 4096)
    
    now = datetime.now(timezone.utc)
    
    return {
        'id': str(uuid4()),
        'provider': map_provider_from_config(config),
        'provider_type': 'llm',
        'name': config.get('name', name),
        'api_key': api_key,
        'base_url': base_url,
        'default_model': model,
        'available_models': json.dumps([model] if model else []),
        'max_tokens': max_tokens,
        'temperature': 0.7,
        'is_active': is_active,
        'is_default': False,
        'priority': 0,
        'description': f"从 yiliu 导入: {name}",
        
        'support_reference_image': False,
        'support_multiple_reference_images': False,
        'reference_image_field': 'image',
        'usage_count': 0,
        'total_cost': 0.0,
        
        'created_at': now,
        'updated_at': now,
    }


def check_exists(session, name: str, base_url: str) -> bool:
    """检查连接器是否已存在"""
    result = session.execute(
        text("SELECT id FROM ai_connectors WHERE name = :name AND base_url = :base_url"),
        {'name': name, 'base_url': base_url}
    )
    return result.first() is not None


def import_image_providers(session) -> int:
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
            connector_dict = transform_image_provider(name, config)
            
            # 检查是否已存在
            if check_exists(session, connector_dict['name'], connector_dict['base_url']):
                print(f"    ⚠️  已存在，跳过: {connector_dict['name']}")
                continue
            
            # 插入数据库
            session.execute(ai_connectors_table.insert().values(**connector_dict))
            count += 1
            print(f"    ✅ 已添加: {connector_dict['name']} (ID: {connector_dict['id'][:8]}...)")
            
        except Exception as e:
            print(f"    ❌ 错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    session.commit()
    print(f"\n  ✅ 成功导入 {count} 个图像生成提供商")
    return count


def import_text_providers(session) -> int:
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
            connector_dict = transform_text_provider(name, config)
            
            # 检查是否已存在
            if check_exists(session, connector_dict['name'], connector_dict['base_url']):
                print(f"    ⚠️  已存在，跳过: {connector_dict['name']}")
                continue
            
            # 插入数据库
            session.execute(ai_connectors_table.insert().values(**connector_dict))
            count += 1
            print(f"    ✅ 已添加: {connector_dict['name']} (ID: {connector_dict['id'][:8]}...)")
            
        except Exception as e:
            print(f"    ❌ 错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    session.commit()
    print(f"\n  ✅ 成功导入 {count} 个文本生成提供商")
    return count


def list_existing_connectors(session):
    """列出已有的连接器"""
    print("\n📋 已有的 AI 连接器:")
    
    result = session.execute(text("SELECT name, provider_type, is_active FROM ai_connectors"))
    rows = result.fetchall()
    
    if not rows:
        print("  (无)")
        return
    
    for row in rows:
        status = '✅ 启用' if row[2] else '❌ 禁用'
        print(f"  - {row[0]} ({row[1]}) - {status}")


# =============================================================================
# 主函数
# =============================================================================

def main():
    print("=" * 80)
    print("🚀 YLCraft - 导入 yiliu 配置 (v2 - SQLAlchemy Core)")
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
    
    with SessionLocal() as session:
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
