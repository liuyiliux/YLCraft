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
import asyncio
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from urllib.parse import parse_qs

from app.db.models.book_source import BookSource as DBBookSource
from app.services.novel.source_parser import (
    BookSource,
    parse_book_source_json,
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


def _build_search_url(search_url_template: str, keyword: str, base_url: str, page: int = 1) -> dict:
    """
    根据 Legado 模板构建实际搜索 URL 和请求参数
    支持:
      - 简单替换: {{key}} {{page}}
      - 相对路径: /search -> base_url + /search
      - @js: 前缀格式
      - java.md5Encode() 等 JS 表达式
      - POST请求: url,{"method":"POST","body":"..."} 格式
    
    返回: {"url": str, "method": "GET"/"POST", "data": dict/none}
    """
    result = {"url": "", "method": "GET", "data": None}
    url = search_url_template.strip()
    
    # 解析 Legado 附加参数（逗号后的JSON配置）
    extra_config = {}
    if ',' in url and '://' in url:
        parts = url.split(',', 1)
        url = parts[0]
        try:
            if parts[1].strip().startswith('{'):
                extra_config = json.loads(parts[1].strip())
        except Exception as e:
            pass
    
    # 去掉 @js: 前缀
    is_js = False
    if url.startswith('@js:'):
        url = url[4:].strip()
        is_js = True
    
    # 处理 JS 表达式
    if is_js:
        ctx = {'key': keyword, 'page': page, 'base_url': base_url}
        url = _eval_js_expr(url, ctx)
        result["url"] = url if url.startswith('http') else ''
        result["method"] = extra_config.get("method", "GET")
        # 如果是 POST 请求，处理 body 变量替换
        if result["method"].upper() == "POST":
            body_str = extra_config.get("body", "")
            body_str = body_str.replace('{{key}}', keyword).replace('{{keyword}}', keyword)
            body_str = body_str.replace('{{page}}', str(page)).replace('{key}', keyword).replace('{page}', str(page))
            if '=' in body_str:
                parsed = parse_qs(body_str)
                result["data"] = {k: v[0] for k, v in parsed.items()}
            else:
                result["data"] = body_str
        return result
    
    # 相对路径：拼接 base_url
    if url and not url.startswith(('http://', 'https://', '@', '{{')):
        if base_url:
            url = base_url.rstrip('/') + '/' + url.lstrip('/')
    
    # 简单替换
    url = url.replace('{{key}}', keyword).replace('{{keyword}}', keyword)
    url = url.replace('{{page}}', str(page)).replace('{key}', keyword).replace('{page}', str(page))
    
    result["url"] = url
    
    # 处理 POST 请求
    if extra_config.get("method", "").upper() == "POST":
        result["method"] = "POST"
        body_str = extra_config.get("body", "")
        # 替换 body 中的变量
        body_str = body_str.replace('{{key}}', keyword).replace('{{keyword}}', keyword)
        body_str = body_str.replace('{{page}}', str(page)).replace('{key}', keyword).replace('{page}', str(page))
        # 解析 form body
        if '=' in body_str:
            parsed = parse_qs(body_str)
            result["data"] = {k: v[0] for k, v in parsed.items()}
        else:
            result["data"] = body_str

    return result


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
                    "ruleExplore": json.loads(source_dict["rule_explore"]) if source_dict.get("rule_explore") else None,
                    "source_id": source_dict.get("id"),
                    "enabled_by_user": source_dict.get("enabled_by_user", True),
                    # 新增字段
                    "cookie": source_dict.get("cookie"),
                    "header": source_dict.get("header"),
                    "loginUrl": source_dict.get("login_url"),
                    "loginUi": source_dict.get("login_ui"),
                    "loginCheckJs": source_dict.get("login_check_js"),
                    "coverUrl": source_dict.get("cover_url"),
                    "bookSourceComment": source_dict.get("book_source_comment"),
                    "weight": source_dict.get("weight", 0),
                    "respondTime": source_dict.get("respond_time", 0),
                    "lastUpdateTime": source_dict.get("last_update_time"),
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
                        SET book_source_name = :name,
                            book_source_type = :type,
                            enabled = :enabled,
                            rule_search = :search,
                            rule_book_info = :info,
                            rule_toc = :toc,
                            rule_content = :content,
                            rule_explore = :rule_explore,
                            book_source_group = :group,
                            cookie = :cookie,
                            header = :header,
                            loginUrl = :loginUrl,
                            loginUi = :loginUi,
                            loginCheckJs = :loginCheckJs,
                            coverUrl = :coverUrl,
                            bookSourceComment = :comment,
                            weight = :weight,
                            respondTime = :respondTime,
                            lastUpdateTime = :lastUpdateTime
                        WHERE book_source_url = :url
                    """),
                    {
                        "name": source.bookSourceName,
                        "type": source.bookSourceType,
                        "enabled": source.enabled,
                        "search": json.dumps(source.ruleSearch) if source.ruleSearch else "",
                        "info": json.dumps(source.ruleBookInfo) if source.ruleBookInfo else "",
                        "toc": json.dumps(source.ruleToc) if source.ruleToc else "",
                        "content": json.dumps(source.ruleContent) if source.ruleContent else "",
                        "rule_explore": json.dumps(source.ruleExplore) if source.ruleExplore else "",
                        "group": source.bookSourceGroup or "",
                        "cookie": source.cookie or "",
                        "header": source.header or "",
                        "loginUrl": source.loginUrl or "",
                        "loginUi": source.loginUi or "",
                        "loginCheckJs": source.loginCheckJs or "",
                        "coverUrl": source.coverUrl or "",
                        "comment": source.bookSourceComment or "",
                        "weight": source.weight or 0,
                        "respondTime": source.respondTime or 0,
                        "lastUpdateTime": str(source.lastUpdateTime) if source.lastUpdateTime else "",
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
                         cookie, header, loginUrl, loginUi, loginCheckJs,
                         coverUrl, bookSourceComment, weight, respondTime, lastUpdateTime,
                         created_at, updated_at)
                        VALUES 
                        (:id, :name, :url, :type, :enabled,
                         :search, :info, :toc, :content, :rule_explore,
                         :group, :enabled_by_user, :custom_order, :search_url, :explore,
                         :cookie, :header, :loginUrl, :loginUi, :loginCheckJs,
                         :coverUrl, :comment, :weight, :respondTime, :lastUpdateTime,
                         :created_at, :updated_at)
                    """),
                    {
                        "id": source.source_id,
                        "name": source.bookSourceName,
                        "url": source.bookSourceUrl,
                        "type": source.bookSourceType,
                        "enabled": source.enabled,
                        "search": json.dumps(source.ruleSearch) if source.ruleSearch else "",
                        "info": json.dumps(source.ruleBookInfo) if source.ruleBookInfo else "",
                        "toc": json.dumps(source.ruleToc) if source.ruleToc else "",
                        "content": json.dumps(source.ruleContent) if source.ruleContent else "",
                        "rule_explore": json.dumps(source.ruleExplore) if source.ruleExplore else "",
                        "group": source.bookSourceGroup or "",
                        "enabled_by_user": source.enabled_by_user,
                        "custom_order": source.customOrder or 0,
                        "search_url": source.searchUrl or "",
                        "explore": source.explore or False,
                        "cookie": source.cookie or "",
                        "header": source.header or "",
                        "loginUrl": source.loginUrl or "",
                        "loginUi": source.loginUi or "",
                        "loginCheckJs": source.loginCheckJs or "",
                        "coverUrl": source.coverUrl or "",
                        "comment": source.bookSourceComment or "",
                        "weight": source.weight or 0,
                        "respondTime": source.respondTime or 0,
                        "lastUpdateTime": str(source.lastUpdateTime) if source.lastUpdateTime else "",
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
        """删除书源（先数据库，再内存，保证一致性）"""
        if not self.db:
            # 无数据库时直接操作内存
            source = self.get_source(source_id)
            if source:
                self.sources.remove(source)
                return True
            return False
        
        # 先操作数据库
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
            return False
        
        # 数据库成功后，再修改内存
        source = self.get_source(source_id)
        if source:
            self.sources.remove(source)
        return True

    def batch_delete_sources(self, source_ids: List[str]) -> Dict[str, Any]:
        """批量删除书源（先数据库，再内存，保证一致性）"""
        if not self.db:
            # 无数据库时直接操作内存
            deleted = 0
            failed = 0
            for source_id in source_ids:
                source = self.get_source(source_id)
                if source:
                    self.sources.remove(source)
                    deleted += 1
                else:
                    failed += 1
            return {"success": failed == 0, "deleted": deleted, "failed": failed}
        
        # 先操作数据库
        failed = 0
        try:
            # SQLite 不支持 IN :tuple，需要展开参数
            placeholders = ', '.join(f':id{i}' for i in range(len(source_ids)))
            params = {f'id{i}': sid for i, sid in enumerate(source_ids)}
            self.db.execute(
                text(f"DELETE FROM book_sources WHERE id IN ({placeholders})"),
                params
            )
            self.db.commit()
        except Exception as e:
            print(f"批量删除书源失败: {e}")
            if self.db:
                self.db.rollback()
            return {"success": False, "deleted": 0, "failed": len(source_ids)}
        
        # 数据库成功后，再修改内存，并正确计数
        deleted = 0
        for source_id in source_ids:
            source = self.get_source(source_id)
            if source:
                self.sources.remove(source)
                deleted += 1
        
        return {"success": True, "deleted": deleted, "failed": 0}

    def batch_toggle_sources(self, source_ids: List[str], enabled: bool) -> Dict[str, Any]:
        """批量启用/禁用书源（先数据库，再内存，保证一致性）"""
        if not self.db:
            # 无数据库时直接操作内存
            updated = 0
            failed = 0
            for source_id in source_ids:
                source = self.get_source(source_id)
                if source:
                    source.enabled_by_user = enabled
                    updated += 1
                else:
                    failed += 1
            return {"success": failed == 0, "updated": updated, "failed": failed}
        
        # 先操作数据库
        try:
            # SQLite 不支持 IN :tuple，需要展开参数
            placeholders = ', '.join(f':id{i}' for i in range(len(source_ids)))
            params = {f'id{i}': sid for i, sid in enumerate(source_ids)}
            params['enabled'] = enabled
            self.db.execute(
                text(f"UPDATE book_sources SET enabled_by_user = :enabled WHERE id IN ({placeholders})"),
                params
            )
            self.db.commit()
        except Exception as e:
            print(f"批量切换书源状态失败: {e}")
            if self.db:
                self.db.rollback()
            return {"success": False, "updated": 0, "failed": len(source_ids)}
        
        # 数据库成功后，再修改内存
        updated = 0
        failed = 0
        for source_id in source_ids:
            source = self.get_source(source_id)
            if source:
                source.enabled_by_user = enabled
                updated += 1
            else:
                failed += 1
        
        return {"success": failed == 0, "updated": updated, "failed": failed}
    
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

    def _build_headers(self, source: BookSource) -> Dict[str, str]:
        """
        构建请求头（模拟真实浏览器）
        参考 Legado AnalyzeUrl.kt 的 headerMap 处理
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # 添加 Referer（参考 Legado 的 baseUrl 处理）
        if source.bookSourceUrl:
            headers["Referer"] = source.bookSourceUrl
        
        # 添加自定义请求头（如果书源配置了 header 字段）
        # 参考 Legado 的 source.getHeaderMap()
        if hasattr(source, 'header') and source.header:
            try:
                custom_headers = json.loads(source.header) if isinstance(source.header, str) else source.header
                if isinstance(custom_headers, dict):
                    headers.update(custom_headers)
            except Exception:
                pass
        
        # 添加 Cookie（如果书源配置了 cookie 字段）
        # 参考 Legado 的 CookieManager
        if hasattr(source, 'cookie') and source.cookie:
            headers["Cookie"] = source.cookie
        
        return headers

    async def search_all_sources(self, keyword: str, max_concurrent: int = 10) -> List[Dict[str, Any]]:
        """
        在所有启用的书源中搜索（并发版本）
        参考 Legado 的 mapParallelSafe 实现
        """
        # 收集所有需要搜索的书源
        sources_to_search = [
            source for source in self.sources
            if source.enabled_by_user and source.ruleSearch and self._is_compatible_source(source)
        ]
        
        if not sources_to_search:
            return []
        
        # 使用信号量限制并发数（参考 Legado 的线程池控制）
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def search_with_semaphore(source):
            """带信号量的搜索（限制并发数）"""
            async with semaphore:
                try:
                    results = await self._search_single_source(source, keyword)
                    for r in results:
                        r["sourceName"] = source.bookSourceName
                        r["sourceUrl"] = source.bookSourceUrl
                        r["sourceId"] = source.source_id
                    return results
                except Exception as e:
                    print(f"在书源 {source.bookSourceName} 搜索失败: {e}")
                    return []
        
        # 并发执行所有搜索任务
        print(f"开始并发搜索 {len(sources_to_search)} 个书源（并发数={max_concurrent}）...")
        start_time = time.time()
        
        tasks = [search_with_semaphore(source) for source in sources_to_search]
        all_results_list = await asyncio.gather(*tasks)
        
        # 展平结果
        all_results = []
        for results in all_results_list:
            all_results.extend(results)
        
        elapsed = time.time() - start_time
        print(f"搜索完成，耗时 {elapsed:.2f} 秒，找到 {len(all_results)} 条结果")
        
        # 统一字段名以匹配前端期望
        # 前端期望: title, author, url, cover, source_site, source_id
        # 后端返回: name, author, url, sourceName, sourceUrl, sourceId
        normalized_results = []
        for book in all_results:
            normalized_results.append({
                "title": book.get("name", ""),
                "author": book.get("author", ""),
                "url": book.get("url", ""),
                "cover": book.get("cover", ""),
                "source_site": book.get("sourceName", ""),
                "source_id": book.get("sourceId", ""),
            })
        
        return normalized_results
    
    async def _search_single_source(self, source: BookSource, keyword: str) -> List[Dict[str, Any]]:
        """在单个书源中搜索，支持 JS 模板，带重试逻辑"""
        if not source.ruleSearch:
            return []
        
        # 构建搜索 URL 和请求参数
        try:
            search_config = _build_search_url(source.searchUrl or "", keyword, source.bookSourceUrl, page=1)
            search_url = search_config["url"]
            method = search_config.get("method", "GET")
            data = search_config.get("data")
        except Exception as e:
            print(f"构建URL失败 [{source.bookSourceName}]: {e}")
            return []
        
        if not search_url:
            print(f"[{source.bookSourceName}] URL为空, template={source.searchUrl}")
            return []
        
        if not search_url.startswith(("http://", "https://")):
            print(f"[{source.bookSourceName}] URL不合法: {search_url[:80]}")
            return []
        
        # 构建请求头（参考 Legado）
        headers = self._build_headers(source)

        # 调试：打印实际发出的请求信息
        
        # 重试逻辑（参考 Legado 的 retry 字段）
        max_retries = getattr(source, 'retry', 3) or 3  # 默认3次重试
        timeout = getattr(source, 'timeout', 30) or 30  # 默认30秒超时（参考 Legado）
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout, connect=10.0),
                    follow_redirects=True,
                    verify=False
                ) as client:
                    # 根据 method 选择 GET 或 POST
                    if method.upper() == "POST" and data:
                        response = await client.post(search_url, data=data, headers=headers)
                    else:
                        response = await client.get(search_url, headers=headers)
                    
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
                print(f"[{source.bookSourceName}] 请求超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # 指数退避
                    continue
                return []
            
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                
                if status == 403:
                    print(f"[{source.bookSourceName}] HTTP 403 被拒绝")
                    print(f"  可能原因：需要登录/Cookie过期/反爬")
                    print(f"  请求头: {headers}")
                    # 403 不重试，直接返回空结果
                    return []
                
                elif status in [429, 503, 504]:  # 限流或临时错误，可以重试
                    print(f"[{source.bookSourceName}] HTTP {status}，将重试 (尝试 {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 * (attempt + 1))  # 指数退避
                        continue
                    return []
                
                else:
                    print(f"[{source.bookSourceName}] HTTP错误 {status}: {e.request.url}")
                    return []
            
            except Exception as e:
                print(f"[{source.bookSourceName}] 失败: {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return []
        
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
