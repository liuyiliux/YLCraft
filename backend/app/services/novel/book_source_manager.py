"""
书源管理服务
支持导入/导出/管理阅读App格式的书源
"""

import json
import os
import re
import time
import hashlib
import base64
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.models.book_source import BookSource as DBBookSource
from app.services.novel.source_parser import (
    BookSource, parse_book_source_json,
    parse_book_list, parse_chapter_list,
    parse_chapter_content, parse_book_info
)
from app.services.novel.crawler import NovelCrawler
import httpx


def _java_md5(s: str) -> str:
    """模拟 java.md5Encode()"""
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def _java_base64(s: str) -> str:
    """模拟 java.base64Encode()"""
    return base64.b64encode(s.encode('utf-8')).decode('utf-8')


def _preprocess_java(expr: str) -> str:
    """
    预处理 JS 表达式中的 java.* 调用
    把 java.md5Encode(X) 和 java.base64Encode(X) 替换成实际值
    """
    # 递归处理嵌套调用，最多 5 层
    for _ in range(5):
        changed = False
        new_expr = expr

        # 处理 java.md5Encode("...")
        def replace_md5(m):
            nonlocal changed, new_expr
            inner = m.group(1)
            if 'java.' in inner:
                return m.group(0)
            s = inner.strip().strip('"\'')
            result = _java_md5(s)
            changed = True
            return f'"{result}"'
        new_expr = re.sub(r'java\.md5Encode\(([^()]+)\)', replace_md5, new_expr)

        # 处理 java.base64Encode("...")
        def replace_base64(m):
            nonlocal changed, new_expr
            inner = m.group(1)
            if 'java.' in inner:
                return m.group(0)
            s = inner.strip().strip('"\'')
            result = _java_base64(s)
            changed = True
            return f'"{result}"'
        new_expr = re.sub(r'java\.base64Encode\(([^()]+)\)', replace_base64, new_expr)

        if not changed:
            break
        expr = new_expr

    return expr


def _eval_js_expr(expr: str, context: dict) -> str:
    """
    执行 Legado JS 模板表达式
    先用 Python 处理 java.* 调用，再用 Python eval 计算结果
    """
    try:
        key = context.get('key', '')
        page = int(context.get('page', 1))
        base_url = context.get('base_url', '')

        # 预处理：替换 java.* 调用
        expr = _preprocess_java(expr)

        # 替换变量
        expr = expr.replace('{{key}}', f'"{key}"')
        expr = expr.replace('{{keyword}}', f'"{key}"')
        expr = expr.replace('{{page}}', str(page))
        expr = expr.replace('{key}', f'"{key}"')
        expr = expr.replace('{page}', str(page))
        expr = expr.replace('{baseUrl}', f'"{base_url}"')

        # 处理 Math.round(new Date()/1000)
        expr = re.sub(r'Math\.round\(new\s*Date\(\)\s*/\s*1000\s*\)',
                      str(int(time.time())), expr)
        # 处理 Date.now()
        expr = re.sub(r'Date\.now\(\)', str(int(time.time() * 1000)), expr)

        # 处理字符串拼接，如 "hello" + key + "world"
        # 把 +key+ 替换成实际的字符串值
        if '"' in expr:
            # 处理 "prefix" + key + "suffix" 格式
            def replace_key_concat(m):
                prefix = m.group(1)
                suffix = m.group(2)
                return f'"{prefix}{key}{suffix}"'
            expr = re.sub(r'"([^"]*)"\s*\+\s*key\s*\+\s*"([^"]*)"', replace_key_concat, expr)

            # 处理 "string" + "string"
            try:
                # 简单处理：把 "a" + "b" 合并成 "ab"
                while '"+"' in expr or "'+'" in expr:
                    expr = re.sub(r'"([^"]*)"\s*\+\s*"([^"]*)"', lambda m: f'"{m.group(1)}{m.group(2)}"', expr)
                    expr = re.sub(r"'([^']*)'\s*\+\s*'([^']*)'", lambda m: f"'{m.group(1)}{m.group(2)}'", expr)
            except Exception:
                pass

        # 用 Python eval 计算简单表达式
        try:
            result = eval(f'f{expr}' if expr.startswith('"') or expr.startswith("'") else expr)
            return str(result) if result else ''
        except Exception:
            pass

        return expr

    except Exception as e:
        print(f"JS处理失败: {expr}, 错误: {e}")
        return ''


def _build_search_url(search_url_template: str, keyword: str, base_url: str, page: int = 1) -> str:
    """
    根据 Legado 模板构建实际搜索 URL
    支持:
      - 简单替换: {{key}} {{page}}
      - 相对路径: /search -> base_url + /search
      - @js: 前缀格式
      - java.md5Encode() 等 JS 表达式
    """
    url = search_url_template.strip()

    # 去掉 @js: 前缀
    is_js = False
    if url.startswith('@js:'):
        url = url[4:].strip()
        is_js = True

    # 处理 JS 表达式
    if is_js:
        ctx = {'key': keyword, 'page': page, 'base_url': base_url}
        url = _eval_js_expr(url, ctx)
        return url if url.startswith('http') else ''

    # 相对路径：拼接 base_url
    if url and not url.startswith(('http://', 'https://', '@', '{{')):
        if base_url:
            url = base_url.rstrip('/') + '/' + url.lstrip('/')

    # 简单替换
    url = url.replace('{{key}}', keyword).replace('{{keyword}}', keyword)
    url = url.replace('{{page}}', str(page)).replace('{key}', keyword).replace('{page}', str(page))

    # 去掉 Legado 附加参数（如 ,{"charset":"gbk"}）
    if ',' in url and '://' in url:
        parts = url.split(',', 1)
        if parts[1].strip().startswith('{'):
            url = parts[0]

    return url


class BookSourceManager:
    """书源管理器"""
    
    def __init__(self, db: Session = None):
        self.db = db
        self.sources: List[BookSource] = []
        self._load_sources()
    
    def _load_sources(self):
        """从数据库加载书源"""
        if self.db is None:
            self._load_from_file()
            return
        
        try:
            result = self.db.execute(text("SELECT * FROM book_sources"))
            rows = result.fetchall()
            
            for row in rows:
                source_dict = dict(row._mapping)
                mapped = {
                    "bookSourceName": source_dict.get("book_source_name"),
                    "bookSourceUrl": source_dict.get("book_source_url"),
                    "bookSourceType": source_dict.get("book_source_type"),
                    "enabled": source_dict.get("enabled"),
                    "customOrder": source_dict.get("custom_order"),
                    "searchUrl": source_dict.get("search_url"),
                    "bookSourceGroup": source_dict.get("book_source_group"),
                    "ruleSearch": json.loads(source_dict["rule_search"]) if source_dict.get("rule_search") else None,
                    "ruleBookInfo": json.loads(source_dict["rule_book_info"]) if source_dict.get("rule_book_info") else None,
                    "ruleToc": json.loads(source_dict["rule_toc"]) if source_dict.get("rule_toc") else None,
                    "ruleContent": json.loads(source_dict["rule_content"]) if source_dict.get("rule_content") else None,
                    "source_id": source_dict.get("id"),
                    "enabled_by_user": source_dict.get("enabled_by_user", True),
                }
                try:
                    source = BookSource(**mapped)
                    self.sources.append(source)
                except Exception as e:
                    print(f"加载书源失败: {e}, data: {mapped}")
        except Exception as e:
            print(f"从数据库加载书源失败: {e}")
            self._load_from_file()
    
    def _load_from_file(self):
        """从默认文件加载书源（兼容旧版）"""
        default_path = "app/services/novel/default_sources.json"
        if os.path.exists(default_path):
            try:
                with open(default_path, 'r', encoding='utf-8') as f:
                    json_str = f.read()
                self.sources = parse_book_source_json(json_str)
            except Exception as e:
                print(f"从文件加载书源失败: {e}")
    
    def import_sources(self, json_str: str) -> Dict[str, Any]:
        """导入书源JSON"""
        try:
            new_sources = parse_book_source_json(json_str)
        except Exception as e:
            return {"success": False, "error": str(e), "added": 0, "updated": 0, "failed": 0}
        
        added = 0
        updated = 0
        failed = 0
        
        for source in new_sources:
            try:
                existing = next((s for s in self.sources 
                               if s.bookSourceUrl == source.bookSourceUrl), None)
                
                if existing:
                    existing.__dict__.update(source.__dict__)
                    updated += 1
                else:
                    source.source_id = self._generate_id()
                    self.sources.append(source)
                    added += 1
                
                if self.db:
                    if not self._save_source_to_db(source):
                        failed += 1
                        continue
            except Exception as e:
                print(f"导入书源失败 {source.bookSourceName}: {e}")
                failed += 1
        
        return {
            "success": failed == 0,
            "added": added,
            "updated": updated,
            "failed": failed,
            "total": len(self.sources),
            "error": f"失败 {failed} 个" if failed > 0 else None
        }
    
    def _generate_id(self) -> str:
        """生成书源ID"""
        import uuid
        return str(uuid.uuid4())
    
    def _save_source_to_db(self, source: BookSource) -> bool:
        """保存书源到数据库，返回是否成功"""
        if self.db is None:
            return False
        
        try:
            result = self.db.execute(
                text("SELECT id FROM book_sources WHERE book_source_url = :url"),
                {"url": source.bookSourceUrl}
            )
            existing = result.fetchone()
            
            if existing:
                self.db.execute(
                    text("""
                        UPDATE book_sources 
                        SET book_source_name = :name, book_source_type = :type, 
                            enabled = :enabled, rule_search = :search, 
                            rule_book_info = :info, rule_toc = :toc, 
                            rule_content = :content, rule_explore = :rule_explore,
                            book_source_group = :group
                        WHERE book_source_url = :url
                    """),
                    {
                        "name": source.bookSourceName,
                        "type": source.bookSourceType,
                        "enabled": source.enabled,
                        "search": json.dumps(source.ruleSearch) if source.ruleSearch else None,
                        "info": json.dumps(source.ruleBookInfo) if source.ruleBookInfo else None,
                        "toc": json.dumps(source.ruleToc) if source.ruleToc else None,
                        "content": json.dumps(source.ruleContent) if source.ruleContent else None,
                        "rule_explore": json.dumps(source.ruleExplore) if source.ruleExplore else None,
                        "group": source.bookSourceGroup,
                        "url": source.bookSourceUrl
                    }
                )
            else:
                from datetime import datetime
                now = datetime.now().isoformat()
                self.db.execute(
                    text("""
                        INSERT INTO book_sources 
                        (id, book_source_name, book_source_url, book_source_type, enabled, 
                         rule_search, rule_book_info, rule_toc, rule_content, rule_explore,
                         book_source_group, enabled_by_user, custom_order, search_url, explore,
                         created_at, updated_at)
                        VALUES (:id, :name, :url, :type, :enabled, 
                                :search, :info, :toc, :content, :rule_explore,
                                :group, :enabled_by_user, :custom_order, :search_url, :explore,
                                :created_at, :updated_at)
                    """),
                    {
                        "id": source.source_id,
                        "name": source.bookSourceName,
                        "url": source.bookSourceUrl,
                        "type": source.bookSourceType,
                        "enabled": source.enabled,
                        "search": json.dumps(source.ruleSearch) if source.ruleSearch else None,
                        "info": json.dumps(source.ruleBookInfo) if source.ruleBookInfo else None,
                        "toc": json.dumps(source.ruleToc) if source.ruleToc else None,
                        "content": json.dumps(source.ruleContent) if source.ruleContent else None,
                        "rule_explore": json.dumps(source.ruleExplore) if source.ruleExplore else None,
                        "group": source.bookSourceGroup,
                        "enabled_by_user": source.enabled_by_user,
                        "custom_order": source.customOrder or 0,
                        "search_url": source.searchUrl or "",
                        "explore": source.explore or False,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            
            self.db.commit()
            return True
        except Exception as e:
            print(f"保存书源到数据库失败: {e}")
            if self.db:
                self.db.rollback()
            return False
    
    def _is_js_source(self, source: BookSource) -> bool:
        """判断书源是否含 Legado JS 特有语法"""
        search_url = source.searchUrl or ""
        if search_url and not search_url.startswith(("http://", "https://")):
            return True
        if '{{' in search_url or '{%' in search_url or '@js' in search_url:
            return True
        for rule_dict in [source.ruleSearch, source.ruleBookInfo, source.ruleToc, source.ruleContent, source.ruleExplore]:
            if rule_dict:
                rule_str = json.dumps(rule_dict, ensure_ascii=False)
                if '"@' in rule_str or "'@" in rule_str or '@js' in rule_str:
                    return True
        return False

    def list_sources(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """列出所有书源"""
        result = []
        for source in self.sources:
            if enabled_only and not source.enabled_by_user:
                continue
            result.append({
                "id": source.source_id,
                "book_source_name": source.bookSourceName,
                "book_source_url": source.bookSourceUrl,
                "book_source_type": source.bookSourceType,
                "book_source_group": source.bookSourceGroup,
                "enabled_by_user": source.enabled_by_user,
                "is_js_source": self._is_js_source(source),
            })
        return result
    
    def get_source(self, source_id: str) -> Optional[BookSource]:
        """获取指定书源"""
        return next((s for s in self.sources if s.source_id == source_id), None)
    
    def toggle_source(self, source_id: str, enabled: bool) -> bool:
        """启用/禁用书源"""
        source = self.get_source(source_id)
        if source:
            source.enabled_by_user = enabled
            if self.db:
                try:
                    self.db.execute(
                        text("UPDATE book_sources SET enabled_by_user = :enabled WHERE id = :id"),
                        {"enabled": enabled, "id": source_id}
                    )
                    self.db.commit()
                except Exception as e:
                    print(f"更新书源状态失败: {e}")
                    if self.db:
                        self.db.rollback()
            return True
        return False
    
    def delete_source(self, source_id: str) -> bool:
        """删除书源"""
        source = self.get_source(source_id)
        if source:
            self.sources.remove(source)
            if self.db:
                try:
                    self.db.execute(
                        text("DELETE FROM book_sources WHERE id = :id"),
                        {"id": source_id}
                    )
                    self.db.commit()
                except Exception as e:
                    print(f"删除书源失败: {e}")
                    if self.db:
                        self.db.rollback()
            return True
        return False
    
    def export_sources(self) -> str:
        """导出所有书源为JSON"""
        sources_dict = []
        for source in self.sources:
            if not source.enabled_by_user:
                continue
            sources_dict.append(source.dict(exclude={"source_id", "enabled_by_user"}, exclude_none=True))
        
        return json.dumps(sources_dict, ensure_ascii=False, indent=2)
    
    def _is_compatible_source(self, source: BookSource) -> bool:
        """判断书源是否兼容（现在支持 JS 模板，基本都兼容）"""
        search_url = source.searchUrl or ""
        if search_url and not search_url.startswith(("http://", "https://", "@js:", "{{")):
            return False
        return True

    async def search_all_sources(self, keyword: str) -> List[Dict[str, Any]]:
        """在所有启用的书源中搜索"""
        all_results = []
        
        for source in self.sources:
            if not source.enabled_by_user or not source.ruleSearch:
                continue

            if not self._is_compatible_source(source):
                continue
            
            try:
                results = await self._search_single_source(source, keyword)
                for r in results:
                    r["sourceName"] = source.bookSourceName
                    r["sourceUrl"] = source.bookSourceUrl
                all_results.extend(results)
            except Exception as e:
                print(f"在书源 {source.bookSourceName} 搜索失败: {e}")
                continue
        
        return all_results
    
    async def _search_single_source(self, source: BookSource, keyword: str) -> List[Dict[str, Any]]:
        """在单个书源中搜索，支持 JS 模板"""
        if not source.ruleSearch:
            return []

        # 构建搜索 URL
        try:
            search_url = _build_search_url(source.searchUrl or "", keyword, source.bookSourceUrl, page=1)
        except Exception as e:
            print(f"构建URL失败 [{source.bookSourceName}]: {e}")
            return []

        if not search_url:
            print(f"[{source.bookSourceName}] URL为空, template={source.searchUrl}")
            return []

        if not search_url.startswith(("http://", "https://")):
            print(f"[{source.bookSourceName}] URL不合法: {search_url[:80]}")
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, verify=False) as client:
                response = await client.get(search_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()
                html = response.text

            if not html.strip():
                print(f"[{source.bookSourceName}] 响应为空")
                return []

            rule = source.ruleSearch
            if isinstance(rule, dict) and any(str(v).startswith('@js:') for v in rule.values()):
                print(f"[{source.bookSourceName}] 含@js:规则，跳过")
                return []

            results = parse_book_list(rule, html, source.bookSourceUrl)
            print(f"[{source.bookSourceName}] 解析到 {len(results)} 条结果")
            return results

        except httpx.TimeoutException:
            print(f"[{source.bookSourceName}] 请求超时")
            return []
        except httpx.HTTPStatusError as e:
            print(f"[{source.bookSourceName}] HTTP错误 {e.response.status_code}: {e.request.url}")
            return []
        except Exception as e:
            print(f"[{source.bookSourceName}] 失败: {type(e).__name__}: {e}")
            return []
    
    async def get_book_info(self, source: BookSource, book_url: str) -> Dict[str, Any]:
        """获取书籍详情"""
        if not source.ruleBookInfo:
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                response = await client.get(book_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()
                html = response.text
            
            info = parse_book_info(source.ruleBookInfo, html, source.bookSourceUrl)
            return info
            
        except Exception as e:
            print(f"获取书籍详情失败: {e}")
            return {}
    
    async def get_chapter_list(self, source: BookSource, toc_url: str) -> List[Dict[str, Any]]:
        """获取章节列表"""
        if not source.ruleToc:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                response = await client.get(toc_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()
                html = response.text
            
            chapters = parse_chapter_list(source.ruleToc, html, toc_url)
            return chapters
            
        except Exception as e:
            print(f"获取章节列表失败: {e}")
            return []
    
    async def get_chapter_content(self, source: BookSource, chapter_url: str) -> Optional[str]:
        """获取章节内容"""
        if not source.ruleContent:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                response = await client.get(chapter_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()
                html = response.text
            
            content = parse_chapter_content(source.ruleContent, html)
            return content
            
        except Exception as e:
            print(f"获取章节内容失败: {e}")
            return None
