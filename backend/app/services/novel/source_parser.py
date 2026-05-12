"""
阅读App(Legado)书源JSON格式解析器
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


def _eval_js_rule(js_code: str, html: str, base_url: str = "", json_data: Any = None) -> Any:
    if not HAS_MINIRACER:
        print("警告: 未安装 py_mini_racer，无法执行 JS 规则")
        return None

    try:
        import json as json_mod
        ctx = MiniRacer()

        # 注入基础变量
        if json_data is not None:
            ctx.execute(f"var result = {json_mod.dumps(json_data, ensure_ascii=False)};")
        else:
            escaped_html = json_mod.dumps(html)
            ctx.execute(f"var result = {escaped_html};")

        ctx.execute(f"var baseUrl = {json_mod.dumps(base_url)};")

        # 内置辅助函数(模拟 Legado 环境)
        helpers = r"""
        function javaMd5(s) { return ''; }
        function javaBase64(s) { return btoa(unescape(encodeURIComponent(s))); }
        function javaStr(s) { return String(s); }
        """
        ctx.execute(helpers)

        # 提取纯 JS 代码(去掉 @js: 前缀 / {{ }} 包裹)
        code = js_code.strip()
        if code.startswith('@js:'):
            code = code[4:].strip()
        elif code.startswith('{{') and code.endswith('}}'):
            code = code[2:-2].strip()

        # 包在 function 里执行，支持 return；同时 result 可能被修改
        wrapped = "(function() {\n" + code + "\n})();"
        ret = ctx.execute(wrapped)

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
