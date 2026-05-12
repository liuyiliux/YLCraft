"""
书源管理服务
支持导入/导出/管理阅读App格式的书源
"""

import json
import os
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


class BookSourceManager:
    """书源管理器"""
    
    def __init__(self, db: Session = None):
        self.db = db
        self.sources: List[BookSource] = []
        self._load_sources()
    
    def _load_sources(self):
        """从数据库加载书源"""
        if self.db is None:
            # 如果没有数据库，从默认文件加载
            self._load_from_file()
            return
        
        try:
            result = self.db.execute(text("SELECT * FROM book_sources WHERE enabled_by_user = 1"))
            rows = result.fetchall()
            
            for row in rows:
                source_dict = dict(row._mapping)
                try:
                    source = BookSource(**source_dict)
                    self.sources.append(source)
                except Exception as e:
                    print(f"加载书源失败: {e}")
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
        """
        导入书源JSON
        
        Args:
            json_str: 书源JSON字符串
            
        Returns:
            导入结果统计
        """
        try:
            new_sources = parse_book_source_json(json_str)
        except Exception as e:
            return {"success": False, "error": str(e), "imported": 0}
        
        added = 0
        updated = 0
        
        for source in new_sources:
            # 检查是否已存在（按bookSourceUrl判断）
            existing = next((s for s in self.sources 
                           if s.bookSourceUrl == source.bookSourceUrl), None)
            
            if existing:
                # 更新现有书源
                existing.__dict__.update(source.__dict__)
                updated += 1
            else:
                # 添加新书源
                source.source_id = self._generate_id()
                self.sources.append(source)
                added += 1
            
            # 保存到数据库
            if self.db:
                self._save_source_to_db(source)
        
        return {
            "success": True,
            "added": added,
            "updated": updated,
            "total": len(self.sources)
        }
    
    def _generate_id(self) -> str:
        """生成书源ID"""
        import uuid
        return str(uuid.uuid4())
    
    def _save_source_to_db(self, source: BookSource):
        """保存书源到数据库"""
        if self.db is None:
            return
        
        try:
            # 检查是否存在
            result = self.db.execute(
                text("SELECT id FROM book_sources WHERE bookSourceUrl = :url"),
                {"url": source.bookSourceUrl}
            )
            existing = result.fetchone()
            
            if existing:
                # 更新
                self.db.execute(
                    text("""
                        UPDATE book_sources 
                        SET bookSourceName = :name, bookSourceType = :type, 
                            enabled = :enabled, ruleSearch = :search, 
                            ruleBookInfo = :info, ruleToc = :toc, 
                            ruleContent = :content, bookSourceGroup = :group
                        WHERE bookSourceUrl = :url
                    """),
                    {
                        "name": source.bookSourceName,
                        "type": source.bookSourceType,
                        "enabled": source.enabled,
                        "search": json.dumps(source.ruleSearch) if source.ruleSearch else None,
                        "info": json.dumps(source.ruleBookInfo) if source.ruleBookInfo else None,
                        "toc": json.dumps(source.ruleToc) if source.ruleToc else None,
                        "content": json.dumps(source.ruleContent) if source.ruleContent else None,
                        "group": source.bookSourceGroup,
                        "url": source.bookSourceUrl
                    }
                )
            else:
                # 插入
                self.db.execute(
                    text("""
                        INSERT INTO book_sources 
                        (id, bookSourceName, bookSourceUrl, bookSourceType, enabled, 
                         ruleSearch, ruleBookInfo, ruleToc, ruleContent, 
                         bookSourceGroup, enabled_by_user)
                        VALUES (:id, :name, :url, :type, :enabled, 
                                :search, :info, :toc, :content, 
                                :group, :enabled_by_user)
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
                        "group": source.bookSourceGroup,
                        "enabled_by_user": source.enabled_by_user
                    }
                )
            
            self.db.commit()
        except Exception as e:
            print(f"保存书源到数据库失败: {e}")
            if self.db:
                self.db.rollback()
    
    def list_sources(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """列出所有书源"""
        result = []
        for source in self.sources:
            if enabled_only and not source.enabled_by_user:
                continue
            result.append({
                "id": source.source_id,
                "name": source.bookSourceName,
                "url": source.bookSourceUrl,
                "type": source.bookSourceType,
                "group": source.bookSourceGroup,
                "enabled": source.enabled_by_user
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
    
    async def search_all_sources(self, keyword: str) -> List[Dict[str, Any]]:
        """
        在所有启用的书源中搜索
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            搜索结果列表
        """
        all_results = []
        
        for source in self.sources:
            if not source.enabled_by_user or not source.ruleSearch:
                continue
            
            try:
                results = await self._search_single_source(source, keyword)
                # 添加书源信息
                for r in results:
                    r["sourceName"] = source.bookSourceName
                    r["sourceUrl"] = source.bookSourceUrl
                all_results.extend(results)
            except Exception as e:
                print(f"在书源 {source.bookSourceName} 搜索失败: {e}")
                continue
        
        return all_results
    
    async def _search_single_source(self, source: BookSource, keyword: str) -> List[Dict[str, Any]]:
        """在单个书源中搜索"""
        if not source.ruleSearch:
            return []
        
        # 构建搜索URL
        search_url = source.searchUrl or f"{source.bookSourceUrl}/search?keyword={keyword}"
        # 替换关键字占位符
        search_url = search_url.replace("{{key}}", keyword).replace("{key}", keyword)
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(search_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                response.raise_for_status()
                html = response.text
            
            # 解析搜索结果
            results = parse_book_list(source.ruleSearch, html, source.bookSourceUrl)
            return results
            
        except Exception as e:
            print(f"搜索 {source.bookSourceName} 失败: {e}")
            return []
    
    async def get_book_info(self, source: BookSource, book_url: str) -> Dict[str, Any]:
        """获取书籍详情"""
        if not source.ruleBookInfo:
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
