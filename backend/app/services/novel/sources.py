"""
YLCraft — 小说书源配置
支持多站点扩展
"""

from typing import Optional
from pydantic import BaseModel


class BookSource(BaseModel):
    """书源配置"""
    id: str
    name: str
    base_url: str
    enabled: bool = True
    
    # 搜索配置
    search_url: str
    search_charset: str = 'utf-8'
    search_rule: dict  # 解析规则
    
    # 目录配置
    catalog_rule: dict
    
    # 章节内容配置
    chapter_rule: dict


# 预设书源配置
BOOK_SOURCES = {
    'biqigecn': {
        'id': 'biqigecn',
        'name': '笔趣阁',
        'base_url': 'https://www.biqigecn.com',
        'enabled': True,
        'search_url': '/search?q={keyword}',
        'search_charset': 'utf-8',
    },
}


def get_source(source_id: str) -> Optional[dict]:
    """获取书源配置"""
    return BOOK_SOURCES.get(source_id)


def list_sources() -> list[dict]:
    """列出所有书源"""
    return [{'id': k, 'name': v['name'], 'enabled': v['enabled']} for k, v in BOOK_SOURCES.items()]
