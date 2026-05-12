"""
阅读App（Legado）书源JSON格式解析器
支持导入和使用阅读App的标准书源格式
"""

import json
import re
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field


class BookSourceRule(BaseModel):
    """书源规则定义"""
    # 搜索规则
    ruleSearch: Optional[Dict[str, Any]] = None
    # 书籍详情规则
    ruleBookInfo: Optional[Dict[str, Any]] = None
    # 目录规则
    ruleToc: Optional[Dict[str, Any]] = None
    # 正文规则
    ruleContent: Optional[Dict[str, Any]] = None
    # 发现规则（可选）
    ruleExplore: Optional[Dict[str, Any]] = None


class BookSource(BaseModel):
    """阅读App书源完整定义"""
    # 书源名称
    bookSourceName: str
    # 书源URL（域名）
    bookSourceUrl: str
    # 书源类型：0=文本，1=音频，2=图片
    bookSourceType: int = 0
    # 是否启用
    enabled: bool = True
    # 自定义排序权重
    customOrder: int = 0
    # 搜索URL（直接搜索用）
    searchUrl: Optional[str] = None
    # 封面URL（相对路径转绝对路径用）
    coverUrl: Optional[str] = None
    # 各种规则
    ruleSearch: Optional[Dict[str, Any]] = None
    ruleBookInfo: Optional[Dict[str, Any]] = None
    ruleToc: Optional[Dict[str, Any]] = None
    ruleContent: Optional[Dict[str, Any]] = None
    ruleExplore: Optional[Dict[str, Any]] = None
    # 分组名称
    bookSourceGroup: Optional[str] = None
    # 是否支持发现
    explore: bool = False
    
    # 以下字段为内部使用，不在JSON中
    source_id: Optional[str] = None  # 内部ID
    enabled_by_user: bool = True  # 用户是否启用


def parse_book_source_json(json_str: str) -> List[BookSource]:
    """
    解析阅读App书源JSON文件
    
    Args:
        json_str: JSON字符串（支持单个书源或书源数组）
        
    Returns:
        书源对象列表
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}")
    
    # 支持单个书源或书源数组
    if isinstance(data, dict):
        data = [data]
    
    if not isinstance(data, list):
        raise ValueError("书源JSON格式错误：应为对象或数组")
    
    sources = []
    for item in data:
        try:
            source = BookSource(**item)
            sources.append(source)
        except Exception as e:
            print(f"跳过无效书源: {e}")
            continue
    
    return sources


def parse_rule_value(rule: Any, html: str, base_url: str = "") -> Any:
    """
    解析规则值
    
    阅读App的规则支持多种格式：
    1. CSS选择器：".title" 或 "div.book-name"
    2. 正则：{"pattern": "regex", "group": 1}
    3. 组合规则："@meta[property=og:title]@content" 
    4. JS脚本：以{{开头，以}}结尾
    
    Args:
        rule: 规则定义
        html: HTML内容
        base_url: 基础URL（用于相对路径转换）
        
    Returns:
        解析结果
    """
    from bs4 import BeautifulSoup
    import re
    
    if rule is None:
        return None
    
    # 如果是字符串规则
    if isinstance(rule, str):
        # JS脚本（暂不支持，返回原值）
        if rule.startswith("{{") and rule.endswith("}}"):
            return None
        
        # CSS选择器
        if rule.startswith("@"):
            # @meta[property=og:title]@content 格式
            return _parse_css_rule(rule, html)
        else:
            # 普通CSS选择器
            return _parse_css_selector(rule, html)
    
    # 如果是字典规则（正则）
    if isinstance(rule, dict):
        pattern = rule.get("pattern", "")
        group = rule.get("group", 0)
        return _parse_regex(pattern, html, group)
    
    return None


def _parse_css_selector(selector: str, html: str) -> Optional[str]:
    """解析CSS选择器"""
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        element = soup.select_one(selector)
        if element:
            return element.get_text(strip=True)
        return None
    except Exception:
        return None


def _parse_css_rule(rule_str: str, html: str) -> Optional[str]:
    """
    解析复杂CSS规则
    例如：@meta[property=og:title]@content
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 解析规则字符串
        # 格式：@tag[attr=value]@attr2
        pattern = r'@(\w+)(?:\[([^\]]+)\])?(?:@(\w+))?'
        match = re.match(pattern, rule_str)
        
        if not match:
            return None
        
        tag = match.group(1)
        condition = match.group(2)
        attr = match.group(3)
        
        if condition:
            # 有条件：meta[property=og:title]
            key, value = condition.split('=')
            elements = soup.find_all(tag, {key: value})
        else:
            elements = soup.find_all(tag)
        
        if not elements:
            return None
        
        if attr:
            return elements[0].get(attr)
        else:
            return elements[0].get_text(strip=True)
            
    except Exception:
        return None


def _parse_regex(pattern: str, html: str, group: int = 0) -> Optional[str]:
    """解析正则表达式"""
    try:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            return match.group(group)
        return None
    except Exception:
        return None


def parse_book_list(rule: Dict[str, Any], html: str, base_url: str) -> List[Dict[str, Any]]:
    """
    解析搜索结果书籍列表
    
    Args:
        rule: ruleSearch规则
        html: 搜索结果页HTML
        base_url: 书源基础URL
        
    Returns:
        书籍列表 [{"name": ..., "bookUrl": ..., "author": ..., "coverUrl": ...}, ...]
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 获取书籍列表容器
        book_list_selector = rule.get("bookList", "")
        if not book_list_selector:
            return []
        
        book_elements = soup.select(book_list_selector)
        books = []
        
        for elem in book_elements:
            book = {}
            
            # 书名
            name_rule = rule.get("name", "")
            if name_rule:
                name_elem = elem.select_one(name_rule) if isinstance(name_rule, str) else None
                book["name"] = name_elem.get_text(strip=True) if name_elem else ""
            
            # 书籍链接
            book_url_rule = rule.get("bookUrl", "")
            if book_url_rule:
                url_elem = elem.select_one(book_url_rule) if isinstance(book_url_rule, str) else None
                if url_elem:
                    href = url_elem.get("href", "")
                    # 处理相对路径
                    if href and not href.startswith("http"):
                        href = base_url.rstrip("/") + "/" + href.lstrip("/")
                    book["bookUrl"] = href
            
            # 作者
            author_rule = rule.get("author", "")
            if author_rule:
                author_elem = elem.select_one(author_rule) if isinstance(author_rule, str) else None
                book["author"] = author_elem.get_text(strip=True) if author_elem else ""
            
            # 封面
            cover_rule = rule.get("coverUrl", "")
            if cover_rule:
                cover_elem = elem.select_one(cover_rule) if isinstance(cover_rule, str) else None
                if cover_elem:
                    src = cover_elem.get("src") or cover_elem.get("data-src", "")
                    # 处理相对路径
                    if src and not src.startswith("http"):
                        src = base_url.rstrip("/") + "/" + src.lstrip("/")
                    book["coverUrl"] = src
            
            # 简介
            intro_rule = rule.get("intro", "")
            if intro_rule:
                intro_elem = elem.select_one(intro_rule) if isinstance(intro_rule, str) else None
                book["intro"] = intro_elem.get_text(strip=True)[:200] if intro_elem else ""
            
            if book.get("name") and book.get("bookUrl"):
                books.append(book)
        
        return books
        
    except Exception as e:
        print(f"解析书籍列表失败: {e}")
        return []


def parse_chapter_list(rule: Dict[str, Any], html: str, base_url: str) -> List[Dict[str, Any]]:
    """
    解析章节列表
    
    Args:
        rule: ruleToc规则
        html: 目录页HTML
        base_url: 书源基础URL
        
    Returns:
        章节列表 [{"name": ..., "url": ...}, ...]
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 获取章节列表容器
        chapter_list_selector = rule.get("chapterList", "")
        if not chapter_list_selector:
            return []
        
        chapter_elements = soup.select(chapter_list_selector)
        chapters = []
        
        for idx, elem in enumerate(chapter_elements, 1):
            chapter = {}
            
            # 章节名
            name_rule = rule.get("chapterName", "")
            if name_rule:
                name_elem = elem.select_one(name_rule) if isinstance(name_rule, str) else elem
                chapter["name"] = name_elem.get_text(strip=True) if name_elem else f"第{idx}章"
            
            # 章节链接
            url_rule = rule.get("chapterUrl", "")
            if url_rule:
                url_elem = elem.select_one(url_rule) if isinstance(url_rule, str) else elem
                if url_elem:
                    href = url_elem.get("href", "")
                    # 处理相对路径
                    if href and not href.startswith("http"):
                        # 如果是相对路径，需要拼接
                        if href.startswith("/"):
                            # 相对于根目录
                            from urllib.parse import urlparse
                            parsed = urlparse(base_url)
                            href = f"{parsed.scheme}://{parsed.netloc}{href}"
                        else:
                            # 相对于当前路径
                            href = base_url.rstrip("/") + "/" + href.lstrip("/")
                    chapter["url"] = href
            
            if chapter.get("name"):
                chapters.append(chapter)
        
        return chapters
        
    except Exception as e:
        print(f"解析章节列表失败: {e}")
        return []


def parse_chapter_content(rule: Dict[str, Any], html: str) -> Optional[str]:
    """
    解析章节内容
    
    Args:
        rule: ruleContent规则
        html: 章节页HTML
        
    Returns:
        章节正文内容（HTML格式）
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 获取内容容器
        content_selector = rule.get("content", "")
        if not content_selector:
            return None
        
        content_elem = soup.select_one(content_selector)
        if not content_elem:
            return None
        
        # 清理内容（移除广告、脚本等）
        for tag in content_elem.find_all(["script", "style", "iframe"]):
            tag.decompose()
        
        # 获取正文HTML
        content = str(content_elem)
        
        # 可选：移除章节标题规则
        remove_rule = rule.get("removeContent", "")
        if remove_rule:
            for rm_elem in content_elem.select(remove_rule):
                rm_elem.decompose()
            content = str(content_elem)
        
        return content
        
    except Exception as e:
        print(f"解析章节内容失败: {e}")
        return None


def parse_book_info(rule: Dict[str, Any], html: str, base_url: str) -> Dict[str, Any]:
    """
    解析书籍详情页
    
    Args:
        rule: ruleBookInfo规则
        html: 详情页HTML
        base_url: 书源基础URL
        
    Returns:
        书籍详情 {"name": ..., "author": ..., "coverUrl": ..., "intro": ..., "tocUrl": ...}
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        info = {}
        
        # 书名
        name_rule = rule.get("name", "")
        if name_rule:
            name_elem = soup.select_one(name_rule) if isinstance(name_rule, str) else None
            info["name"] = name_elem.get_text(strip=True) if name_elem else ""
        
        # 作者
        author_rule = rule.get("author", "")
        if author_rule:
            author_elem = soup.select_one(author_rule) if isinstance(author_rule, str) else None
            info["author"] = author_elem.get_text(strip=True) if author_elem else ""
        
        # 封面
        cover_rule = rule.get("coverUrl", "")
        if cover_rule:
            cover_elem = soup.select_one(cover_rule) if isinstance(cover_rule, str) else None
            if cover_elem:
                src = cover_elem.get("src") or cover_elem.get("data-src", "")
                if src and not src.startswith("http"):
                    src = base_url.rstrip("/") + "/" + src.lstrip("/")
                info["coverUrl"] = src
        
        # 简介
        intro_rule = rule.get("intro", "")
        if intro_rule:
            intro_elem = soup.select_one(intro_rule) if isinstance(intro_rule, str) else None
            info["intro"] = intro_elem.get_text(strip=True)[:500] if intro_elem else ""
        
        # 目录页链接
        toc_url_rule = rule.get("tocUrl", "")
        if toc_url_rule:
            toc_elem = soup.select_one(toc_url_rule) if isinstance(toc_url_rule, str) else None
            if toc_elem:
                href = toc_elem.get("href", "")
                if href and not href.startswith("http"):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                info["tocUrl"] = href
        
        return info
        
    except Exception as e:
        print(f"解析书籍详情失败: {e}")
        return {}
