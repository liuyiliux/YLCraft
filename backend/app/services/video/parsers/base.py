"""
平台解析器基类。
参考 yby6-video-parser-skill 架构设计。
"""
from abc import ABC
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class ParseResult:
    """通用解析返回结果"""
    video_url: str = ""
    images: List[str] = field(default_factory=list)
    cover_url: str = ""
    title: str = ""
    author_name: str = ""
    author_uid: str = ""
    author_avatar: str = ""
    content_type: str = ""
    parse_method: str = ""
    raw: Any = None


class BaseParser(ABC):
    """所有解析器的基类"""
    pass
