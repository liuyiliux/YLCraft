"""
阅读App(Legado)书源JSON格式解析器
支持导入和使用阅读App的标准书源格式
"""

import json
import re
from urllib.parse import urljoin
from typing import Optional, Dict, List, Any, Union
from pydantic import BaseModel, Field

try:
    import jsonpath_ng
    HAS_JSONPATH = True
except ImportError:
    HAS_JSONPATH = False

try:
    from py_mini_racer import MiniRacer
    HAS_MINIRACER = True
except ImportError:
    HAS_MINIRACER = False


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
            new_result = []
            for r in result:
                if isinstance(r, list):
                    new_result.extend(r)
                elif isinstance(r, dict):
                    new_result.extend(r.values())
            result = new_result
        elif '[*]' in part:
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
    if isinstance(rule_val, str) and not rule_val.startswith('$') and not _is_js_rule(rule_val):
        return True
    return False


def _is_js_rule(rule_val: Any) -> bool:
    """判断规则值是否是 JS 规则(@js: 或 {{ }} 格式)"""
    if not isinstance(rule_val, str):
        return False
    s = rule_val.strip()
    if s.startswith('@js:'):
        return True
    if s.startswith('{{') and s.endswith('}}'):
        return True
    return False


# ========== BookSource 模型定义（供 book_source_manager.py 使用）==========

class BookSourceRule(BaseModel):
    """书源规则定义"""
    ruleSearch: Optional[Dict[str, Any]] = None
    ruleBookInfo: Optional[Dict[str, Any]] = None
    ruleToc: Optional[Dict[str, Any]] = None
    ruleContent: Optional[Dict[str, Any]] = None
    ruleExplore: Optional[Dict[str, Any]] = None


class BookSource(BaseModel):
    """阅读App书源完整定义"""
    bookSourceName: str
    bookSourceUrl: str
    bookSourceType: int = 0
    enabled: bool = True
    customOrder: int = 0
    searchUrl: Optional[str] = None
    coverUrl: Optional[str] = None
    ruleSearch: Optional[Dict[str, Any]] = None
    ruleBookInfo: Optional[Dict[str, Any]] = None
    ruleToc: Optional[Dict[str, Any]] = None
    ruleContent: Optional[Dict[str, Any]] = None
    ruleExplore: Optional[Dict[str, Any]] = None
    bookSourceGroup: Optional[str] = None
    explore: bool = False
    
    # Cookie 和自定义请求头（Legado 标准字段）
    cookie: Optional[str] = None
    header: Optional[str] = None
    
    # 登录相关（Legado 标准字段）
    loginUrl: Optional[str] = None
    loginUi: Optional[str] = None
    loginCheckJs: Optional[str] = None
    
    # 其他字段
    bookSourceComment: Optional[str] = None
    weight: int = 0
    respondTime: int = 0
    lastUpdateTime: Optional[Union[int, str]] = None
    
    # 以下字段为内部使用，不在JSON中
    source_id: Optional[str] = None
    enabled_by_user: bool = True
    ruleFormat: str = "legado"
    ruleVersion: Optional[str] = None
    ylcraftRule: Optional[Dict[str, Any]] = None
    originalFormat: Optional[str] = None
    originalSource: Optional[Dict[str, Any]] = None
    migrationLog: Optional[str] = None


# ========== 书源 JSON 解析 ===========

def parse_book_source_json(json_str: str) -> List[BookSource]:
    """
    解析阅读App书源JSON文件
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}")

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


# ========== HTML/CSS 解析函数 ===========

def parse_rule_value(rule: Any, html: str, base_url: str = "") -> Any:
    """解析规则值（CSS选择器 / 正则 / JS脚本）"""
    from bs4 import BeautifulSoup
    import re

    if rule is None:
        return None

    if isinstance(rule, str):
        if rule.startswith("{{") and rule.endswith("}}"):
            return None
        if rule.startswith("@"):
            return _parse_css_rule(rule, html)
        else:
            return _parse_css_selector(rule, html)

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


def _eval_js_rule(js_code: str, result: str) -> str:
    """
    执行 Legado <js> 规则。
    - result: 前置规则的文本结果（Legado 中注入为 JS 变量 result）
    - 返回 JS 执行的字符串结果
    需要 MiniRacer；如果不可用，返回 result 本身。
    """
    if not HAS_MINIRACER:
        print(f"[WARN] MiniRacer 不可用，无法执行 JS 规则: {js_code[:50]}...")
        return result
    try:
        ctx = MiniRacer()
        # 将 result 注入为 JS 变量
        ctx.eval(f"var result = {json.dumps(result)};")
        # 执行 JS 代码，返回最后表达式的值
        val = ctx.eval(js_code)
        return str(val) if val is not None else result
    except Exception as e:
        print(f"[WARN] JS 规则执行失败: {e}")
        return result


def _parse_css_rule(rule_str: str, html: str) -> Optional[str]:
    """
    解析复杂CSS规则，支持 Legado 语法，返回文本结果。
    - 标准CSS: "div.class"
    - @语法链: "class.grid@tag.tr" (逐层查找)
    - @text: "tag.td.2@text" (获取文本)
    - @html: "tag.div@html" (获取HTML)
    - @attr: "tag.a@href" (获取属性)
    - !N 索引: "tag.tr!0" (排除第N个)
    - .N 索引: "tag.td.0" (选择第N个)
    - ##regex: 从结果文本中移除匹配 regex 的部分（Legado 语义）
    - <js>...</js>: 用 JS 处理 result 变量
    """
    from bs4 import BeautifulSoup, Tag
    import re
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 处理 <js>...</js> 语法（Legado JS 规则）
        js_match = re.search(r'<js>(.*?)</js>', rule_str, re.DOTALL)
        js_code = None
        if js_match:
            js_code = js_match.group(1)
            # 去掉 <js>...</js> 部分，保留前面的 CSS 规则
            rule_str = rule_str[:js_match.start()].rstrip().rstrip('@')
        
        # 处理 ## 过滤（Legado 语义：从结果文本中移除匹配部分）
        filter_regex = None
        if '##' in rule_str and not rule_str.startswith('##'):
            parts = rule_str.split('##', 1)
            rule_str = parts[0]
            filter_regex = parts[1]
        
        # 按 @ 分割规则（Legado 语法）
        if '@' in rule_str:
            parts = rule_str.split('@')
            
            # 提取指令（@text, @html, @attr）
            directive = None
            if len(parts) > 1:
                last = parts[-1]
                # 常见指令：text, html, 以及属性名 (href, src, etc.)
                if last == 'text':
                    directive = 'text'
                    parts = parts[:-1]
                elif last == 'html':
                    directive = 'html'
                    parts = parts[:-1]
                elif re.match(r'^[a-zA-Z][a-zA-Z0-9\-]*$', last):
                    # 看起来像属性名（如 href, src, title, data-src 等）
                    directive = last
                    parts = parts[:-1]
            
            elements = [soup]
            selector_parts = [part for part in parts if part]
            if directive and not selector_parts:
                first_element = soup.find(True)
                elements = [first_element] if first_element else [soup]
            
            for i, part in enumerate(parts):
                if not part:
                    continue
                    
                new_elements = []
                for elem in elements:
                    if not isinstance(elem, Tag) and not isinstance(elem, list):
                        continue
                    
                    # 解析选择器（支持 !N 排除 和 .N 选择）
                    selector, filter_type, indices = _parse_selector(part)
                    
                    if isinstance(elem, Tag):
                        found = elem.select(selector)
                        new_elements.extend(found)
                    elif isinstance(elem, list):
                        for e in elem:
                            if isinstance(e, Tag):
                                found = e.select(selector)
                                new_elements.extend(found)
                
                # 应用索引过滤（Legado 语义：!N=排除，.N=选择）
                if filter_type is not None:
                    new_elements = _apply_index_filter(
                        new_elements, filter_type, indices, len(new_elements)
                    )
                
                elements = new_elements if new_elements else []
                if not elements:
                    return None
            
            # 应用指令，获取原始结果
            result_text = None
            if elements and isinstance(elements[0], Tag):
                elem = elements[0]
                if directive == 'text':
                    result_text = elem.get_text(strip=True)
                elif directive == 'html':
                    result_text = str(elem)
                elif directive and isinstance(directive, str):
                    result_text = elem.get(directive) or ""
                else:
                    # 默认返回文本
                    result_text = elem.get_text(strip=True)
            
            # 应用 ## 过滤（Legado 语义：从文本中移除匹配 regex 的部分）
            if result_text is not None and filter_regex:
                print(f"[DEBUG] _parse_css_rule: before ## regex, text='{result_text[:100]}'")
                result_text = re.sub(filter_regex, '', result_text)
                print(f"[DEBUG] _parse_css_rule: after ## regex, text='{result_text[:100]}'")
            
            # 应用 <js> 规则（Legado 语义：用 JS 处理 result 变量）
            if result_text is not None and js_code is not None:
                print(f"[DEBUG] _parse_css_rule: before <js>, text='{result_text[:100]}'")
                result_text = _eval_js_rule(js_code, result_text)
                print(f"[DEBUG] _parse_css_rule: after <js>, text='{result_text[:100]}'")
            
            if result_text is not None:
                return result_text
            
            return None
            
        else:
            # 标准CSS选择器
            element = soup.select_one(rule_str)
            if element:
                result_text = element.get_text(strip=True)
                if filter_regex:
                    result_text = re.sub(filter_regex, '', result_text)
                return result_text
            return None
    except Exception as e:
        print(f"解析CSS规则失败 '{rule_str}': {e}")
        return None


def _parse_selector(rule_part: str) -> tuple:
    """
    解析 Legado 选择器，支持索引语法。
    Legado 源码参考: AnalyzeByJSoup.kt -> ElementsSingle.findIndexSet()
    
    索引语法:
    - "tag.tr.0"       -> 只选择索引0（include）
    - "tag.tr!0"       -> 排除索引0（exclude）
    - "tag.tr.0.2"     -> 只选择索引0和2
    - "tag.tr!0!2"     -> 排除索引0和2
    - "tag.tr[0:10:2]" -> 支持区间（暂未实现）
    
    返回: (css_selector, filter_type, indices)
    - filter_type: None(不过滤), 'include', 'exclude'
    - indices: int 列表（已处理负数）
    """
    import re
    
    filter_type = None
    indices = []
    selector = rule_part.strip()
    
    # 先处理 !N 语法（排除），从右向左读取
    # 匹配末尾的 !数字（支持多个 !N）
    if '!' in selector:
        # 从末尾开始，收集所有的 !N
        temp_selector = selector
        temp_indices = []
        # 用正则找出所有 !N 片段
        # 注意：只处理末尾连续的 !N，不处理中间的
        # 例如 "tag.tr!0!2" -> selector="tag.tr", indices=[0,2]
        parts = selector.split('!')
        # parts[0] = selector, parts[1:] = index parts
        if len(parts) > 1:
            candidate_selector = parts[0]
            all_digits = True
            for idx_part in parts[1:]:
                if not idx_part.lstrip('-').isdigit():
                    all_digits = False
                    break
            if all_digits:
                filter_type = 'exclude'
                indices = [int(p) for p in parts[1:]]
                selector = candidate_selector
    
    # 再处理 .N 语法（选择），从右向左读取
    # 注意：.N 必须紧跟在选择器末尾，且 N 是数字
    # "tag.td.0" -> selector="tag.td", indices=[0]
    # 注意：不能把 "class.s2" 中的 ".s2" 误判为索引
    if filter_type is None and re.search(r'\.\d+$', selector):
        # 检查末尾的 .数字 是否真的是索引（而不是 CSS 类选择器的一部分）
        # 简单判断：如果选择器以 tag./class./id# 开头，则 .N 是索引
        # 如果选择器已经是 CSS（包含 .class 或 #id），则 .N 可能是 CSS 的一部分
        candidate = re.sub(r'\.\d+$', '', selector)
        if candidate != selector:
            # 检查去掉 .N 后，剩下的部分是否是有效的 Legado 选择器前缀
            # tag.td -> valid, class.s2 -> valid, #id -> valid
            # 但 "a.0" 中的 .0 不是索引（它是 CSS 的一部分）... 
            # 实际上在 Legado 中，.N 索引只出现在 Legado 特殊语法后面
            # 安全的做法：只有以 tag./class./id# 开头时，才把末尾 .N 当索引
            if re.match(r'^(tag|class|id)#?\.', candidate):
                filter_type = 'include'
                indices = [int(re.search(r'\.(\d+)$', selector).group(1))]
                selector = candidate
    
    # 转换 Legado 特殊前缀为 CSS 选择器
    selector = selector.strip()
    if selector.startswith('tag.'):
        selector = selector[4:]  # 去掉 "tag." 前缀
    elif selector.startswith('class.'):
        selector = '.' + selector[6:]  # 转换为 .classname
    elif selector.startswith('id#'):
        selector = '#' + selector[3:]  # 转换为 #id (id#xxx 格式)
    elif selector.startswith('id.') and not selector.startswith('id#'):
        selector = '#' + selector[3:]  # 转换为 #xxx (id.xxx 格式，Legado 常见写法)
    # 否则 selector 已经是标准 CSS
    
    return (selector, filter_type, indices)


def _apply_index_filter(elements: list, filter_type: str, indices: list, neg: int) -> list:
    """
    应用索引过滤（Legado 语义）。
    filter_type: None(不过滤), 'include'(只保留), 'exclude'(排除)
    indices: 索引列表（可能包含负数，需要 +neg 转正）
    neg: len(elements)
    """
    if not indices:
        return elements
    
    # 将负数索引转正
    normalized = []
    for idx in indices:
        if idx < 0:
            idx = neg + idx
        if 0 <= idx < neg:
            normalized.append(idx)
    
    if filter_type == 'include':
        return [elements[i] for i in sorted(set(normalized)) if i < len(elements)]
    elif filter_type == 'exclude':
        # 排除指定索引
        exclude_set = set(normalized)
        return [e for i, e in enumerate(elements) if i not in exclude_set]
    
    return elements


def _select_elements(rule_str: str, html_or_soup: Any) -> list:
    """
    解析 Legado 风格的规则，返回匹配的元素列表（不是文本！）
    支持:
    - 标准CSS: "div.class" -> 返回所有匹配的 elements
    - @语法链: "class.grid@tag.tr" -> 先找 .grid，再在里面找 tr
    - !N 索引: "tag.tr!0" -> 排除索引为 N 的元素（Legado 语义）
    - .N 索引: "tag.td.0" -> 只选择索引为 N 的元素
    - ##过滤: "selector##regex" -> 对文本做正则过滤（移除匹配部分）
    """
    from bs4 import BeautifulSoup, Tag
    import re
    
    if isinstance(html_or_soup, str):
        soup = BeautifulSoup(html_or_soup, 'html.parser')
    else:
        soup = html_or_soup
    
    # 处理 ## 过滤语法（Legado 语义：从结果文本中移除匹配部分）
    filter_regex = None
    if '##' in rule_str:
        parts = rule_str.split('##', 1)
        rule_str = parts[0]
        filter_regex = parts[1]
    
    # 按 @ 分割规则
    if '@' in rule_str:
        parts = rule_str.split('@')
        elements = [soup]
        
        for i, part in enumerate(parts):
            if not part:
                continue
            
            # 解析选择器和处理索引（支持 !N 排除 和 .N 选择）
            selector, filter_type, indices = _parse_selector(part)
            
            new_elements = []
            for elem in elements:
                if isinstance(elem, Tag):
                    found = elem.select(selector)
                    new_elements.extend(found)
                elif isinstance(elem, list):
                    for e in elem:
                        if isinstance(e, Tag):
                            found = e.select(selector)
                            new_elements.extend(found)
            
            # 应用索引过滤（Legado 语义：!N=排除，.N=选择）
            if filter_type is not None:
                new_elements = _apply_index_filter(
                    new_elements, filter_type, indices, len(new_elements)
                )
            
            elements = new_elements if new_elements else []
            if not elements:
                return []
        
        # 应用 ## 过滤（Legado 语义：从文本中移除匹配部分）
        if filter_regex:
            import re
            filtered = []
            for elem in elements:
                text = elem.get_text(strip=True) if isinstance(elem, Tag) else str(elem)
                if re.search(filter_regex, text):
                    filtered.append(elem)
            return filtered
        
        return elements
    
    else:
        # 标准CSS选择器，返回所有匹配元素
        return soup.select(rule_str)



def _parse_regex(pattern: str, html: str, group: int = 0) -> Optional[str]:
    """解析正则表达式"""
    try:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            return match.group(group)
        return None
    except Exception:
        return None


def _absolute_url(url: str, base_url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    return urljoin(base_url.rstrip("/") + "/", value)


# ========== 书列表解析 ===========

def parse_book_list(rule: Dict[str, Any], html: str, base_url: str) -> List[Dict[str, Any]]:
    """解析搜索结果书籍列表，支持 HTML（Legado规则）和 JSON（JSONPath）两种格式"""
    from bs4 import BeautifulSoup
    import json as json_mod
    
    try:
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
        
        soup = BeautifulSoup(html, 'html.parser')
        book_list_selector = rule.get("bookList", "")
        if not book_list_selector or _is_jsonpath_rule(book_list_selector):
            return []
        
        print(f"[DEBUG] parse_book_list: bookList='{book_list_selector}'")
        
        # 使用 _select_elements 解析 Legado 风格规则，返回元素列表
        book_elements = _select_elements(book_list_selector, soup)
        print(f"[DEBUG] parse_book_list: found {len(book_elements)} book_elements")
        
        books = []
        
        for idx, elem in enumerate(book_elements):
            book = {}
            elem_html = str(elem)
            
            # 解析 name 规则
            name_rule = rule.get("name", "")
            name = ""
            if name_rule and isinstance(name_rule, str) and not _is_jsonpath_rule(name_rule):
                name = _parse_css_rule(name_rule, elem_html) or ""
                print(f"[DEBUG] parse_book_list: book[{idx}] name='{name}', rule='{name_rule}'")
                book["name"] = name
            
            # 解析 bookUrl 规则
            book_url_rule = rule.get("bookUrl", "")
            url = ""
            if book_url_rule and isinstance(book_url_rule, str) and not _is_jsonpath_rule(book_url_rule):
                url = _parse_css_rule(book_url_rule, elem_html) or ""
                url = _absolute_url(url, base_url)
                print(f"[DEBUG] parse_book_list: book[{idx}] url='{url}', rule='{book_url_rule}'")
                book["bookUrl"] = url
            
            # 解析 author 规则
            author_rule = rule.get("author", "")
            if author_rule and isinstance(author_rule, str) and not _is_jsonpath_rule(author_rule):
                author = _parse_css_rule(author_rule, elem_html) or ""
                print(f"[DEBUG] parse_book_list: book[{idx}] author='{author}'")
                book["author"] = author
            
            if book.get("name") and book.get("bookUrl"):
                books.append(book)
                print(f"[DEBUG] parse_book_list: book[{idx}] ADDED: {book['name']}")
        
        print(f"[DEBUG] parse_book_list: total {len(books)} books parsed")
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

        if _is_jsonpath_rule(book_list_expr):
            books_data = _eval_jsonpath(book_list_expr, json_data)
        elif isinstance(json_data, list):
            books_data = json_data
        elif isinstance(json_data, dict):
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
                href = _absolute_url(href, base_url)
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
                src = _absolute_url(src, base_url)
                book["coverUrl"] = src

            if book.get("name") and book.get("bookUrl"):
                books.append(book)

        return books

    except Exception as e:
        print(f"解析JSON书籍列表失败: {e}")
        return []


# ========== 章节列表解析 ===========

def parse_chapter_list(rule: Dict[str, Any], html: str, base_url: str) -> List[Dict[str, Any]]:
    """解析章节列表，支持 HTML（Legado规则）和 JSON 两种格式"""
    from bs4 import BeautifulSoup
    import json as json_mod
    
    try:
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
        
        # 使用 _select_elements 解析 Legado 风格规则
        chapter_elements = _select_elements(chapter_list_selector, soup)
        print(f"[DEBUG parse_chapter_list] selector='{chapter_list_selector}', found={len(chapter_elements)} elements")
        if len(chapter_elements) == 0:
            # 打印关键 DOM 结构帮助调试
            list_elem = soup.find(id='list')
            if list_elem:
                print(f"[DEBUG] 找到 id=list 元素, tag={list_elem.name}, 子元素数={len(list_elem.contents)}, 内HTML前200字: {str(list_elem)[:200]}")
            else:
                print(f"[DEBUG] 未找到 id=list 元素. body下直接子元素: {[c.name for c in (soup.body or [])][:20]}")
                # 查找所有含 dd 的容器
                for dd in soup.find_all('dd')[:3]:
                    parent = dd.parent
                    print(f"[DEBUG] 找到 <dd>, 父元素: {parent.name}, class={parent.get('class')}, id={parent.get('id')}")

            dd_elems = soup.select('dd')
            print(f"[DEBUG] 全页 <dd> 数量: {len(dd_elems)}")
            if dd_elems:
                print(f"[DEBUG] 第一个 <dd> 的HTML: {str(dd_elems[0])[:300]}")

        chapters = []

        for idx, elem in enumerate(chapter_elements, 1):
            chapter = {}
            elem_html = str(elem)
            
            name_rule = rule.get("chapterName", "")
            if name_rule and isinstance(name_rule, str) and not _is_jsonpath_rule(name_rule):
                chapter["name"] = _parse_css_rule(name_rule, elem_html) or f"第{idx}章"
            
            url_rule = rule.get("chapterUrl", "")
            if url_rule and isinstance(url_rule, str) and not _is_jsonpath_rule(url_rule):
                url = _parse_css_rule(url_rule, elem_html) or ""
                url = _absolute_url(url, base_url)
                chapter["url"] = url
            
            if chapter.get("name") and chapter.get("url"):
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
                href = _absolute_url(href, base_url)
                chapter["url"] = href

            if chapter.get("name"):
                chapters.append(chapter)
        return chapters
    except Exception as e:
        print(f"解析JSON章节列表失败: {e}")
        return []


# ========== 章节内容解析 ===========

def _parse_content_rule(content_rule: str) -> tuple:
    """
    解析 Legado 内容规则中的混合语法。
    支持格式如: "$..content##filter@js:code"
    返回: (selector, filter_regex, js_code)
    """
    import re
    
    filter_regex = None
    js_code = None
    selector = content_rule.strip()
    
    # 1. 提取 @js: 之后的 JS 代码
    if '@js:' in selector:
        parts = selector.split('@js:', 1)
        selector = parts[0].rstrip('\n')
        js_code = parts[1].strip()
    
    # 2. 提取 ## 之后的过滤正则
    if '##' in selector:
        parts = selector.split('##', 1)
        selector = parts[0].rstrip('\n')
        filter_regex = parts[1].strip()
    
    # 3. 清理 selector：如果包含 JSONPath 符号，尝试提取 CSS 选择器
    # 常见模式：如 "$..content" 后紧跟实际的 CSS 选择器
    if selector.startswith('$') or selector.startswith('$.'):
        # 尝试找实际的 CSS 选择器（通常在换行后）
        lines = selector.split('\n')
        css_lines = [l for l in lines if l.strip() and not l.strip().startswith('$')]
        if css_lines:
            selector = css_lines[0].strip()
        else:
            selector = ''
    
    # 4. 如果 selector 仍然包含 $ 或空，尝试常见选择器
    if not selector or selector.startswith('$'):
        # 尝试常见的小说正文选择器
        selector = '#content'
    
    return selector.strip(), filter_regex, js_code


def parse_chapter_content(rule: Dict[str, Any], html: str) -> Optional[str]:
    """解析章节内容，支持 HTML 和 JSON，支持 Legado 混合语法（##过滤、@js:代码）"""
    import json as json_mod
    import re
    from bs4 import BeautifulSoup, Tag

    try:
        content_rule = rule.get("content", "")
        
        # 解析混合规则语法
        selector, filter_regex, js_code = _parse_content_rule(content_rule)
        
        # 1. 尝试 JSON 解析（如果 content_rule 指向 JSON 数据）
        if content_rule.strip().startswith(('$', '[', '{')):
            try:
                data = json_mod.loads(html.strip())
                if _is_jsonpath_rule(content_rule.split('##')[0].split('@js:')[0].strip()):
                    expr = content_rule.split('##')[0].split('@js:')[0].strip()
                    results = _eval_jsonpath(expr, data)
                    if results:
                        content = str(results[0])
                        if filter_regex:
                            content = re.sub(filter_regex, '', content)
                        return content
            except Exception:
                pass

        soup = BeautifulSoup(html, 'html.parser')
        
        # 2. 使用 CSS 选择器获取内容
        if not selector:
            return None
        
        # 使用 _select_elements 支持 Legado @ 链语法
        content_elems = _select_elements(selector, soup)
        if not content_elems or not isinstance(content_elems[0], Tag):
            return None
        content_elem = content_elems[0]

        for tag in content_elem.find_all(["script", "style", "iframe"]):
            tag.decompose()

        remove_rule = rule.get("removeContent", "")
        if remove_rule and not _is_jsonpath_rule(remove_rule):
            for rm_elem in content_elem.select(remove_rule):
                rm_elem.decompose()

        content = str(content_elem)
        
        # 3. 应用过滤正则（## 语法）
        if filter_regex:
            content = re.sub(filter_regex, '', content)
        
        # 4. 执行 JS 代码（@js: 语法）- 需要 MiniRacer，这里做简化处理
        if js_code and HAS_MINIRACER:
            try:
                from py_mini_racer import MiniRacer
                ctx = MiniRacer()
                escaped_content = content.replace('`', '\\`')
                ctx.eval(f"var result = `{escaped_content}`")
                # 添加 decode 函数（如果有）
                if 'decode(' in js_code:
                    ctx.eval("""
                        function decode(s) {
                            try {
                                return decodeURIComponent(escape(atob(s)));
                            } catch(e) {
                                return s;
                            }
                        }
                    """)
                result = ctx.eval(js_code.replace('result', 'result'))
                if result:
                    content = str(result)
            except Exception as e:
                print(f"[WARN] JS 执行失败: {e}")
        
        return content if content else None

    except Exception as e:
        print(f"解析章节内容失败: {e}")
        return None


# ========== 书籍详情解析 ===========

def parse_book_info(rule: Dict[str, Any], html: str, base_url: str) -> Dict[str, Any]:
    """解析书籍详情页，支持 HTML 和 JSON"""
    import json as json_mod
    from bs4 import BeautifulSoup

    try:
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

        soup = BeautifulSoup(html, 'html.parser')
        info = {}

        name_rule = rule.get("name", "")
        if name_rule and not _is_jsonpath_rule(name_rule):
            info["name"] = _parse_css_rule(name_rule, html) or ""

        author_rule = rule.get("author", "")
        if author_rule and not _is_jsonpath_rule(author_rule):
            info["author"] = _parse_css_rule(author_rule, html) or ""

        cover_rule = rule.get("coverUrl", "")
        if cover_rule and not _is_jsonpath_rule(cover_rule):
            src = _parse_css_rule(cover_rule, html) or ""
            src = _absolute_url(src, base_url)
            info["coverUrl"] = src

        intro_rule = rule.get("intro", "")
        if intro_rule and not _is_jsonpath_rule(intro_rule):
            info["intro"] = (_parse_css_rule(intro_rule, html) or "")[:500]

        toc_url_rule = rule.get("tocUrl", "")
        if toc_url_rule and not _is_jsonpath_rule(toc_url_rule):
            href = _parse_css_rule(toc_url_rule, html) or ""
            href = _absolute_url(href, base_url)
            info["tocUrl"] = href

        return info
    except Exception as e:
        print(f"解析书籍详情失败: {e}")
        return {}


# ========== JS 规则执行（新增，支持 Legado @js: 和 {{ }} 格式）==========

def _eval_js_rule(js_code: str, html: str, base_url: str = "", json_data: Any = None) -> Any:
    """
    执行 Legado JS 规则
    支持 @js: 前缀 和 {{ }} 包裹的 JS 表达式
    """
    if not HAS_MINIRACER:
        print("警告: 未安装 py_mini_racer，无法执行 JS 规则")
        return None

    try:
        import json as json_mod
        ctx = MiniRacer()

        # 安全地注入基础变量
        if json_data is not None:
            ctx.eval(f"var result = JSON.parse({json_mod.dumps(json_mod.dumps(json_data, ensure_ascii=False))});")
        else:
            ctx.eval(f"var result = {json_mod.dumps(html)};")

        ctx.eval(f"var baseUrl = {json_mod.dumps(base_url)};")

        # 内置辅助函数(模拟 Legado 环境)
        helpers = r"""
        function javaMd5(s) { return ''; }
        function javaBase64(s) { return btoa(unescape(encodeURIComponent(s))); }
        function javaStr(s) { return String(s); }
        """
        ctx.eval(helpers)

        # 提取纯 JS 代码(去掉 @js: 前缀 / {{ }} 包裹)
        code = js_code.strip()
        if code.startswith('@js:'):
            code = code[4:].strip()
        elif code.startswith('{{') and code.endswith('}}'):
            code = code[2:-2].strip()

        # 包在函数里执行，支持 return；同时 result 可能被修改
        wrapped = "(function() {\n" + code + "\n})();"
        ret = ctx.eval(wrapped)

        # 优先用函数返回值；如果是 undefined 则读 result
        try:
            if ret is None:
                result = ctx.eval("result")
                return result
            return ret
        except Exception:
            try:
                result = ctx.eval("result")
                return result
            except Exception:
                return ret

    except Exception as e:
        print(f"执行 JS 规则失败: {e}")
        return None
