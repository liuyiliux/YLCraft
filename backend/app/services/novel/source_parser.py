"""
阅读App（Legado）书源JSON格式解析器
支持导入和使用阅读App的标准书源格式
"""

import json
import re
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field

try:
    import jsonpath_ng
    HAS_JSONPATH = True
except ImportError:
    HAS_JSONPATH = False


def _eval_jsonpath(expr: str, data: Any) -> List[Any]:
    """简单的 JSONPath 求值，支持 $.field[*] 格式"""
    if not HAS_JSONPATH:
        return _manual_jsonpath(expr, data)
    try:
        matches = jsonpath_ng.parse(expr).find(data)
        return [m.value for m in matches]
    except Exception:
        return _manual_jsonpath(expr, data)


def _manual_jsonpath(expr: str, data: Any) -> List[Any]:
    """手动实现简单 JSONPath"""
    expr = expr.strip()
    if not expr.startswith('$'):
        return [data] if isinstance(data, dict) else []
    
    # 去掉 $ 或 $.
    path = expr[1:]
    if path.startswith('.'):
        path = path[1:]
    
    result = [data]
    for part in path.split('.'):
        if not part:
            continue
        if part == '*':
            # 展开所有数组/字典
            new_result = []
            for r in result:
                if isinstance(r, list):
                    new_result.extend(r)
                elif isinstance(r, dict):
                    new_result.extend(r.values())
            result = new_result
        elif '[*]' in part:
            # 数组通配
            field = part.replace('[*]', '')
            new_result = []
            for r in result:
                val = r.get(field, []) if isinstance(r, dict) else []
                if isinstance(val, list):
                    new_result.extend(val)
                else:
                    new_result.append(val)
            result = new_result
        else:
            # 普通字段访问
            new_result = []
            for r in result:
                if isinstance(r, dict) and part in r:
                    new_result.append(r[part])
            result = new_result
    
    return result


def _get_json_value(data: Any, expr: str) -> str:
    """从 JSON 数据中提取单个值"""
    results = _eval_jsonpath(expr, data)
    if not results:
        return ''
    val = results[0]
    if isinstance(val, dict):
        return val.get('text', val.get('name', ''))
    return str(val) if val else ''


def _is_jsonpath_rule(rule_val: Any) -> bool:
    """判断规则值是否是 JSONPath 表达式"""
    if isinstance(rule_val, str) and rule_val.startswith('$'):
        return True
    return False


def _is_html_rule(rule_val: Any) -> bool:
    """判断规则值是否是 HTML/CSS 选择器"""
    if isinstance(rule_val, str) and not rule_val.startswith('$') and not rule_val.startswith('@js'):
        return True
    return False


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
    支持 HTML（CSS选择器）和 JSON（JSONPath）两种格式
    """
    from bs4 import BeautifulSoup
    import json as json_mod
    
    try:
        # 判断响应是 JSON 还是 HTML
        is_json = False
        json_data = None
        try:
            stripped = html.strip()
            if stripped.startswith('{') or stripped.startswith('['):
                json_data = json_mod.loads(stripped)
                is_json = True
        except Exception:
            is_json = False
        
        if is_json and json_data is not None:
            return _parse_book_list_json(rule, json_data, base_url)
        
        # HTML 解析
        soup = BeautifulSoup(html, 'html.parser')
        
        book_list_selector = rule.get("bookList", "")
        if not book_list_selector or _is_jsonpath_rule(book_list_selector):
            return []
        
        book_elements = soup.select(book_list_selector)
        books = []
        
        for elem in book_elements:
            book = {}
            
            name_rule = rule.get("name", "")
            if name_rule and isinstance(name_rule, str) and not name_rule.startswith('$'):
                name_elem = elem.select_one(name_rule)
                book["name"] = name_elem.get_text(strip=True) if name_elem else ""
            
            book_url_rule = rule.get("bookUrl", "")
            if book_url_rule and isinstance(book_url_rule, str) and not book_url_rule.startswith('$'):
                url_elem = elem.select_one(book_url_rule)
                if url_elem:
                    href = url_elem.get("href", "")
                    if href and not href.startswith("http"):
                        href = base_url.rstrip("/") + "/" + href.lstrip("/")
                    book["bookUrl"] = href
            
            author_rule = rule.get("author", "")
            if author_rule and isinstance(author_rule, str) and not author_rule.startswith('$'):
                author_elem = elem.select_one(author_rule)
                book["author"] = author_elem.get_text(strip=True) if author_elem else ""
            
            cover_rule = rule.get("coverUrl", "")
            if cover_rule and isinstance(cover_rule, str) and not cover_rule.startswith('$'):
                cover_elem = elem.select_one(cover_rule)
                if cover_elem:
                    src = cover_elem.get("src") or cover_elem.get("data-src", "")
                    if src and not src.startswith("http"):
                        src = base_url.rstrip("/") + "/" + src.lstrip("/")
                    book["coverUrl"] = src
            
            intro_rule = rule.get("intro", "")
            if intro_rule and isinstance(intro_rule, str) and not intro_rule.startswith('$'):
                intro_elem = elem.select_one(intro_rule)
                book["intro"] = intro_elem.get_text(strip=True)[:200] if intro_elem else ""
            
            if book.get("name") and book.get("bookUrl"):
                books.append(book)
        
        return books
        
    except Exception as e:
        print(f"解析书籍列表失败: {e}")
        return []


def _parse_book_list_json(rule: Dict[str, Any], json_data: Any, base_url: str) -> List[Dict[str, Any]]:
    """解析 JSON 格式的搜索结果"""
    try:
        book_list_expr = rule.get("bookList", "")
        if not book_list_expr:
            return []
        
        # 获取书籍列表
        if _is_jsonpath_rule(book_list_expr):
            books_data = _eval_jsonpath(book_list_expr, json_data)
        elif isinstance(json_data, list):
            books_data = json_data
        elif isinstance(json_data, dict):
            # 尝试常见字段
            for key in ["data", "books", "list", "result"]:
                if key in json_data and isinstance(json_data[key], list):
                    books_data = json_data[key]
                    break
            else:
                books_data = []
        else:
            books_data = []
        
        books = []
        for item in books_data:
            book = {}
            
            name_expr = rule.get("name", "")
            if name_expr:
                if _is_jsonpath_rule(name_expr):
                    val = _eval_jsonpath(name_expr, item)
                    book["name"] = str(val[0]) if val else ""
                elif isinstance(item, dict):
                    book["name"] = item.get(name_expr, "")
            
            url_expr = rule.get("bookUrl", "")
            if url_expr:
                if _is_jsonpath_rule(url_expr):
                    val = _eval_jsonpath(url_expr, item)
                    href = str(val[0]) if val else ""
                elif isinstance(item, dict):
                    href = item.get(url_expr, "")
                else:
                    href = ""
                if href and not href.startswith("http"):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                book["bookUrl"] = href
            
            author_expr = rule.get("author", "")
            if author_expr:
                if _is_jsonpath_rule(author_expr):
                    val = _eval_jsonpath(author_expr, item)
                    book["author"] = str(val[0]) if val else ""
                elif isinstance(item, dict):
                    book["author"] = item.get(author_expr, "")
            
            cover_expr = rule.get("coverUrl", "")
            if cover_expr:
                if _is_jsonpath_rule(cover_expr):
                    val = _eval_jsonpath(cover_expr, item)
                    src = str(val[0]) if val else ""
                elif isinstance(item, dict):
                    src = item.get(cover_expr, "")
                else:
                    src = ""
                if src and not src.startswith("http"):
                    src = base_url.rstrip("/") + "/" + src.lstrip("/")
                book["coverUrl"] = src
            
            if book.get("name") and book.get("bookUrl"):
                books.append(book)
        
        return books
        
    except Exception as e:
        print(f"解析JSON书籍列表失败: {e}")
        return []


def parse_chapter_list(rule: Dict[str, Any], html: str, base_url: str) -> List[Dict[str, Any]]:
    """解析章节列表，支持 HTML 和 JSON"""
    from bs4 import BeautifulSoup
    import json as json_mod
    import urllib.parse
    
    try:
        # 判断响应格式
        is_json = False
        json_data = None
        try:
            stripped = html.strip()
            if stripped.startswith('{') or stripped.startswith('['):
                json_data = json_mod.loads(stripped)
                is_json = True
        except Exception:
            is_json = False
        
        if is_json and json_data is not None:
            return _parse_chapter_list_json(rule, json_data, base_url)
        
        soup = BeautifulSoup(html, 'html.parser')
        chapter_list_selector = rule.get("chapterList", "")
        if not chapter_list_selector or _is_jsonpath_rule(chapter_list_selector):
            return []
        
        chapter_elements = soup.select(chapter_list_selector)
        chapters = []
        
        for idx, elem in enumerate(chapter_elements, 1):
            chapter = {}
            name_rule = rule.get("chapterName", "")
            if name_rule and isinstance(name_rule, str) and not name_rule.startswith('$'):
                name_elem = elem.select_one(name_rule)
                chapter["name"] = name_elem.get_text(strip=True) if name_elem else f"第{idx}章"
            
            url_rule = rule.get("chapterUrl", "")
            if url_rule and isinstance(url_rule, str) and not url_rule.startswith('$'):
                url_elem = elem.select_one(url_rule)
                if url_elem:
                    href = url_elem.get("href", "")
                    if href and not href.startswith("http"):
                        if href.startswith("/"):
                            parsed = urllib.parse.urlparse(base_url)
                            href = f"{parsed.scheme}://{parsed.netloc}{href}"
                        else:
                            href = base_url.rstrip("/") + "/" + href.lstrip("/")
                    chapter["url"] = href
            
            if chapter.get("name"):
                chapters.append(chapter)
        
        return chapters
    except Exception as e:
        print(f"解析章节列表失败: {e}")
        return []


def _parse_chapter_list_json(rule: Dict[str, Any], json_data: Any, base_url: str) -> List[Dict[str, Any]]:
    """解析 JSON 格式的章节列表"""
    try:
        chapter_list_expr = rule.get("chapterList", "")
        if _is_jsonpath_rule(chapter_list_expr):
            chapters_data = _eval_jsonpath(chapter_list_expr, json_data)
        elif isinstance(json_data, list):
            chapters_data = json_data
        else:
            return []
        
        chapters = []
        for idx, item in enumerate(chapters_data, 1):
            chapter = {}
            name_expr = rule.get("chapterName", "")
            if name_expr:
                if _is_jsonpath_rule(name_expr):
                    val = _eval_jsonpath(name_expr, item)
                    chapter["name"] = str(val[0]) if val else f"第{idx}章"
                elif isinstance(item, dict):
                    chapter["name"] = item.get(name_expr, f"第{idx}章")
                else:
                    chapter["name"] = str(item) if item else f"第{idx}章"
            
            url_expr = rule.get("chapterUrl", "")
            if url_expr:
                if _is_jsonpath_rule(url_expr):
                    val = _eval_jsonpath(url_expr, item)
                    href = str(val[0]) if val else ""
                elif isinstance(item, dict):
                    href = item.get(url_expr, "")
                else:
                    href = ""
                if href and not href.startswith("http"):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                chapter["url"] = href
            
            if chapter.get("name"):
                chapters.append(chapter)
        return chapters
    except Exception as e:
        print(f"解析JSON章节列表失败: {e}")
        return []


def parse_chapter_content(rule: Dict[str, Any], html: str) -> Optional[str]:
    """解析章节内容，支持 HTML 和 JSON"""
    import json as json_mod
    from bs4 import BeautifulSoup
    
    try:
        # 尝试 JSON
        try:
            data = json_mod.loads(html.strip())
            content_expr = rule.get("content", "")
            if _is_jsonpath_rule(content_expr):
                results = _eval_jsonpath(content_expr, data)
                return results[0] if results else None
            if isinstance(data, dict):
                for key in ["content", "text", "body", "chapter"]:
                    if key in data:
                        return str(data[key])
        except Exception:
            pass
        
        # HTML 解析
        soup = BeautifulSoup(html, 'html.parser')
        content_selector = rule.get("content", "")
        if not content_selector or _is_jsonpath_rule(content_selector):
            return None
        
        content_elem = soup.select_one(content_selector)
        if not content_elem:
            return None
        
        for tag in content_elem.find_all(["script", "style", "iframe"]):
            tag.decompose()
        
        content = str(content_elem)
        remove_rule = rule.get("removeContent", "")
        if remove_rule and not _is_jsonpath_rule(remove_rule):
            for rm_elem in content_elem.select(remove_rule):
                rm_elem.decompose()
            content = str(content_elem)
        
        return content
    except Exception as e:
        print(f"解析章节内容失败: {e}")
        return None


def parse_book_info(rule: Dict[str, Any], html: str, base_url: str) -> Dict[str, Any]:
    """解析书籍详情页，支持 HTML 和 JSON"""
    import json as json_mod
    from bs4 import BeautifulSoup
    
    try:
        # 尝试 JSON
        try:
            data = json_mod.loads(html.strip())
            if isinstance(data, dict):
                info = {}
                for key in ["name", "title"]:
                    expr = rule.get(key, "")
                    if _is_jsonpath_rule(expr):
                        val = _eval_jsonpath(expr, data)
                        info[key] = str(val[0]) if val else ""
                    elif expr in data:
                        info[key] = data[expr]
                return info
        except Exception:
            pass
        
        # HTML 解析
        soup = BeautifulSoup(html, 'html.parser')
        info = {}
        
        name_rule = rule.get("name", "")
        if name_rule and not _is_jsonpath_rule(name_rule):
            name_elem = soup.select_one(name_rule)
            info["name"] = name_elem.get_text(strip=True) if name_elem else ""
        
        author_rule = rule.get("author", "")
        if author_rule and not _is_jsonpath_rule(author_rule):
            author_elem = soup.select_one(author_rule)
            info["author"] = author_elem.get_text(strip=True) if author_elem else ""
        
        cover_rule = rule.get("coverUrl", "")
        if cover_rule and not _is_jsonpath_rule(cover_rule):
            cover_elem = soup.select_one(cover_rule)
            if cover_elem:
                src = cover_elem.get("src") or cover_elem.get("data-src", "")
                if src and not src.startswith("http"):
                    src = base_url.rstrip("/") + "/" + src.lstrip("/")
                info["coverUrl"] = src
        
        intro_rule = rule.get("intro", "")
        if intro_rule and not _is_jsonpath_rule(intro_rule):
            intro_elem = soup.select_one(intro_rule)
            info["intro"] = intro_elem.get_text(strip=True)[:500] if intro_elem else ""
        
        toc_url_rule = rule.get("tocUrl", "")
        if toc_url_rule and not _is_jsonpath_rule(toc_url_rule):
            toc_elem = soup.select_one(toc_url_rule)
            if toc_elem:
                href = toc_elem.get("href", "")
                if href and not href.startswith("http"):
                    href = base_url.rstrip("/") + "/" + href.lstrip("/")
                info["tocUrl"] = href
        
        return info
    except Exception as e:
        print(f"解析书籍详情失败: {e}")
        return {}
