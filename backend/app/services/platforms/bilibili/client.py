"""
YLCraft — B站平台客户端
支持 API 模式和 Patchright 模式切换
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientConfig,
    ClientMode,
    SearchResult,
    NoteDetail,
    UserProfile,
    SeriesInfo,
    SearchParams,
    SearchType,
)
from .apis import (
    BASE_URL,
    SEARCH_VIDEO,
    SEARCH_USER,
    SEARCH_TYPE_MAP,
    VIDEO_DETAIL,
    VIDEO_PLAYER,
    USER_INFO,
    USER_VIDEOS,
    COMMENTS,
    ORDER_TYPE_MAP,
)

logger = logging.getLogger("ylcraft.platforms.bilibili")


# =============================================================================
# B站签名工具（WBI 签名）
# =============================================================================

class BilibiliSign:
    """B站 WBI 签名工具"""
    
    # 固定的 mixin key（可以动态获取，这里简化）
    MIXIN_KEY = "z8xRb9pKjM2vLqW7nT3fY5hD1aU6cE4"
    
    def __init__(self, img_key: str, sub_key: str):
        self.img_key = img_key
        self.sub_key = sub_key
    
    def sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """对参数进行 WBI 签名"""
        # 简化的签名逻辑（完整实现需要从 localStorage 获取 wbi keys）
        # 这里仅做示例，实际应调用 BilibiliClient.get_wbi_keys()
        
        # 添加时间戳
        params['wts'] = int(time.time())
        
        # 按 key 排序
        sorted_params = sorted(params.items())
        
        # URL 编码
        encoded = urlencode(sorted_params)
        
        # 计算 w_rid（简化版，实际需要 MD5 哈希）
        # 这里省略具体签名算法，参考 MediaCrawler 的 BilibiliSign
        
        return params


# =============================================================================
# B站客户端
# =============================================================================

@register_platform("bili")
class BilibiliClient(BasePlatformClient):
    """
    B站客户端
    支持两种模式：
    1. API 模式：直接调用 B站 Web API（快速）
    2. Patchright 模式：使用浏览器（绕过反爬）
    """
    
    def __init__(self, config: ClientConfig):
        super().__init__(config)
        self._wbi_keys = None  # 缓存 wbi keys
    
    # =========================================================================
    # 实现抽象方法
    # =========================================================================
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头（API 模式用）"""
        headers = {
            "User-Agent": self._get_default_user_agent(),
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
        }
        
        if self.config.cookie:
            headers["Cookie"] = self.config.cookie
        
        return headers
    
    def _get_default_user_agent(self) -> str:
        """获取默认 User-Agent"""
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    
    def _get_platform_domain(self) -> str:
        """获取平台域名"""
        return ".bilibili.com"
    
    # =========================================================================
    # 搜索功能
    # =========================================================================
    
    async def search(self, params: SearchParams) -> List[SearchResult]:
        """
        搜索
        支持类型：video（视频）、user（用户）、article（专栏）
        """
        if params.search_type == SearchType.USER:
            return await self.search_users(params.keyword, params.max_results)
        elif params.search_type == SearchType.ARTICLE:
            return await self.search_articles(params.keyword, params.max_results)
        else:
            return await self.search_videos(
                keyword=params.keyword,
                max_results=params.max_results,
                order=params.extra.get('order', 'totalrank'),
                duration=params.extra.get('duration', 0),
            )
    
    async def search_videos(
        self,
        keyword: str,
        max_results: int = 20,
        order: str = "totalrank",  # totalrank综合 click播放量 pubdate日期
        duration: int = 0,         # 0全部 1十分钟以下 2十分钟到三十分钟 3三十分钟以上
    ) -> List[SearchResult]:
        """
        搜索视频
        https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword=xxx
        """
        self._log(f"Searching videos: {keyword}")
        
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": 1,
            "page_size": min(max_results, 50),  # B站限制每次最多50
            "order_type": ORDER_TYPE_MAP.get(order, 0),
            "duration": duration,
        }
        
        # 添加 WBI 签名（如果需要）
        # params = await self._sign_params(params)
        
        url = f"{BASE_URL}{SEARCH_VIDEO}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_list = data.get("result", [])
                
                results = []
                for item in result_list[:max_results]:
                    results.append(self._parse_video_result(item))
                
                self._log(f"Found {len(results)} videos")
                return results
            else:
                error_msg = response.get("message", "Unknown error") if isinstance(response, dict) else "Request failed"
                self._log(f"Search failed: {error_msg}", "error")
                return []
                
        except Exception as e:
            self._log(f"Search error: {e}", "error")
            return []
    
    async def search_users(
        self,
        keyword: str,
        max_results: int = 20,
    ) -> List[SearchResult]:
        """搜索用户"""
        self._log(f"Searching users: {keyword}")
        
        params = {
            "search_type": "bili_user",
            "keyword": keyword,
            "page": 1,
            "page_size": min(max_results, 50),
        }
        
        url = f"{BASE_URL}{SEARCH_USER}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_list = data.get("result", [])
                
                results = []
                for item in result_list[:max_results]:
                    results.append(self._parse_user_result(item))
                
                return results
            else:
                return []
                
        except Exception as e:
            self._log(f"Search users error: {e}", "error")
            return []
    
    async def search_articles(
        self,
        keyword: str,
        max_results: int = 20,
    ) -> List[SearchResult]:
        """搜索专栏文章"""
        self._log(f"Searching articles: {keyword}")
        
        params = {
            "search_type": "article",
            "keyword": keyword,
            "page": 1,
            "page_size": min(max_results, 50),
        }
        
        url = f"{BASE_URL}{SEARCH_VIDEO}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_list = data.get("result", [])
                
                results = []
                for item in result_list[:max_results]:
                    results.append(self._parse_article_result(item))
                
                return results
            else:
                return []
                
        except Exception as e:
            self._log(f"Search articles error: {e}", "error")
            return []
    
    # =========================================================================
    # 详情获取
    # =========================================================================
    
    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """
        获取视频详情（无水印）
        item_id: bvid 或 aid
        """
        self._log(f"Getting video detail: {item_id}")
        
        # 确定是 bvid 还是 aid
        params = {}
        if item_id.startswith("BV"):
            params["bvid"] = item_id
        else:
            params["aid"] = item_id
        
        url = f"{BASE_URL}{VIDEO_DETAIL}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                return self._parse_video_detail(data)
            else:
                error_msg = response.get("message", "Unknown error") if isinstance(response, dict) else "Request failed"
                self._log(f"Get detail failed: {error_msg}", "error")
                return self._empty_detail(item_id)
                
        except Exception as e:
            self._log(f"Get detail error: {e}", "error")
            return self._empty_detail(item_id)
    
    async def get_video_url_no_watermark(self, bvid: str) -> str:
        """
        获取无水印视频地址
        需要登录 + 完整签名
        """
        self._log(f"Getting no-watermark video URL: {bvid}")
        
        params = {
            "bvid": bvid,
            "qn": 112,  # 1080P
            "fnval": 16,  # dash 格式
        }
        
        # 添加 WBI 签名
        # params = await self._sign_params(params)
        
        url = f"{BASE_URL}{VIDEO_PLAYER}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                dash = data.get("dash", {})
                
                # 获取最高画质的视频地址
                video_list = dash.get("video", [])
                if video_list:
                    return video_list[0].get("baseUrl", "")
                
                # 降级：使用 durl
                durl = data.get("durl", [])
                if durl:
                    return durl[0].get("url", "")
            
            return ""
                
        except Exception as e:
            self._log(f"Get video URL error: {e}", "error")
            return ""
    
    # =========================================================================
    # 用户相关
    # =========================================================================
    
    async def get_user_profile(self, user_id: str) -> UserProfile:
        """获取用户主页信息"""
        self._log(f"Getting user profile: {user_id}")
        
        params = {"mid": user_id}
        url = f"{BASE_URL}{USER_INFO}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                card = data.get("card", {})
                stats = data.get("stats", {})
                
                return UserProfile(
                    id=str(card.get("mid", user_id)),
                    name=card.get("name", ""),
                    avatar=card.get("face", ""),
                    platform="bili",
                    followers=stats.get("follower", 0),
                    following=stats.get("following", 0),
                    total_likes=stats.get("likes", 0),
                    desc=card.get("sign", ""),
                    verified=card.get("vip", {}).get("status", 0) == 1,
                    raw_data=data,
                )
            else:
                return UserProfile(id=user_id, name="", avatar="", platform="bili")
                
        except Exception as e:
            self._log(f"Get user profile error: {e}", "error")
            return UserProfile(id=user_id, name="", avatar="", platform="bili")
    
    async def get_user_videos(
        self,
        user_id: str,
        max_results: int = 20,
        order: str = "pubdate",  # pubdate发布时间 stow收藏 click播放
    ) -> List[SearchResult]:
        """获取用户发布的视频列表"""
        self._log(f"Getting user videos: {user_id}")
        
        params = {
            "mid": user_id,
            "ps": min(max_results, 50),
            "pn": 1,
            "order": order,
            "jsonp": "jsonp",
        }
        
        url = f"{BASE_URL}{USER_VIDEOS}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                video_list = data.get("list", {}).get("vlist", [])
                
                results = []
                for item in video_list[:max_results]:
                    results.append(self._parse_user_video_result(item, user_id))
                
                return results
            else:
                return []
                
        except Exception as e:
            self._log(f"Get user videos error: {e}", "error")
            return []
    
    # =========================================================================
    # 合集相关（B站特有）
    # =========================================================================
    
    async def get_series(self, series_id: str) -> SeriesInfo:
        """获取合集信息（B站叫"系列"）"""
        self._log(f"Getting series: {series_id}")
        
        params = {"series_id": series_id}
        url = f"{BASE_URL}/x/series/archives?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                return SeriesInfo(
                    id=series_id,
                    title=data.get("series", {}).get("name", ""),
                    cover=data.get("series", {}).get("cover", ""),
                    platform="bili",
                    author=data.get("series", {}).get("mid", ""),
                    author_id=str(data.get("series", {}).get("mid", "")),
                    video_ids=[str(v.get("bvid", "")) for v in data.get("archives", [])],
                    total_videos=data.get("page", {}).get("count", 0),
                    raw_data=data,
                )
            else:
                return SeriesInfo(id=series_id, title="", cover="", platform="bili", author="", author_id="")
                
        except Exception as e:
            self._log(f"Get series error: {e}", "error")
            return SeriesInfo(id=series_id, title="", cover="", platform="bili", author="", author_id="")
    
    # =========================================================================
    # 评论
    # =========================================================================
    
    async def get_comments(
        self,
        item_id: str,
        max_results: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """获取评论"""
        self._log(f"Getting comments: {item_id}")
        
        # 确定 type（1: 视频 2: 专栏 11: 短视频）
        type_id = 1  # 默认视频
        
        params = {
            "type": type_id,
            "oid": item_id,
            "next": (page - 1) * 20,
            "pn": page,
        }
        
        url = f"{BASE_URL}{COMMENTS}?{urlencode(params)}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                replies = data.get("replies", [])
                
                comments = []
                for reply in replies[:max_results]:
                    comments.append({
                        "id": reply.get("rpid", ""),
                        "content": reply.get("content", ""),
                        "user": reply.get("member", {}).get("uname", ""),
                        "user_avatar": reply.get("member", {}).get("avatar", ""),
                        "likes": reply.get("like", 0),
                        "time": reply.get("ctime", 0),
                        "replies": reply.get("rcount", 0),  # 回复数
                    })
                
                return comments
            else:
                return []
                
        except Exception as e:
            self._log(f"Get comments error: {e}", "error")
            return []
    
    # =========================================================================
    # 解析方法
    # =========================================================================
    
    def _parse_video_result(self, item: Dict) -> SearchResult:
        """解析视频搜索结果"""
        return SearchResult(
            id=item.get("bvid", ""),
            title=item.get("title", ""),
            desc=item.get("description", ""),
            author=item.get("author", ""),
            author_id=str(item.get("mid", "")),
            cover=item.get("pic", ""),
            url=f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            platform="bili",
            type="video",
            likes=item.get("like", 0),
            comments=item.get("review", 0),
            shares=0,  # B站搜索结果没有分享数
            views=item.get("play", 0),
            duration=item.get("duration", 0),
            create_time=str(item.get("pubdate", "")),
            raw_data=item,
        )
    
    def _parse_user_result(self, item: Dict) -> SearchResult:
        """解析用户搜索结果"""
        return SearchResult(
            id=str(item.get("mid", "")),
            title=item.get("uname", ""),
            desc=item.get("usign", ""),
            author=item.get("uname", ""),
            author_id=str(item.get("mid", "")),
            cover=item.get("upic", ""),
            url=f"https://space.bilibili.com/{item.get('mid', '')}",
            platform="bili",
            type="user",
            followers=item.get("fans", 0),
            videos=item.get("videos", 0),
            raw_data=item,
        )
    
    def _parse_article_result(self, item: Dict) -> SearchResult:
        """解析专栏搜索结果"""
        return SearchResult(
            id=str(item.get("id", "")),
            title=item.get("title", ""),
            desc=item.get("summary", ""),
            author=item.get("author_name", ""),
            author_id=str(item.get("mid", "")),
            cover=item.get("image_urls", [""])[0] if item.get("image_urls") else "",
            url=item.get("url", ""),
            platform="bili",
            type="article",
            views=item.get("stats", {}).get("view", 0),
            likes=item.get("stats", {}).get("like", 0),
            comments=item.get("stats", {}).get("reply", 0),
            raw_data=item,
        )
    
    def _parse_video_detail(self, data: Dict) -> NoteDetail:
        """解析视频详情"""
        # 获取无水印视频地址
        bvid = data.get("bvid", "")
        video_url = ""  # 需要在异步上下文中获取
        
        return NoteDetail(
            id=bvid,
            title=data.get("title", ""),
            desc=data.get("desc", ""),
            author=data.get("owner", {}).get("name", ""),
            author_id=str(data.get("owner", {}).get("mid", "")),
            platform="bili",
            type="video",
            video=video_url,  # 需要单独调用 get_video_url_no_watermark()
            video_cover=data.get("pic", ""),
            duration=data.get("duration", 0),
            likes=data.get("stat", {}).get("like", 0),
            comments=data.get("stat", {}).get("reply", 0),
            shares=data.get("stat", {}).get("share", 0),
            collects=data.get("stat", {}).get("favorite", 0),
            views=data.get("stat", {}).get("view", 0),
            tags=[tag.get("tag_name", "") for tag in data.get("tag", [])],
            create_time=str(data.get("pubdate", "")),
            raw_data=data,
        )
    
    def _parse_user_video_result(self, item: Dict, user_id: str) -> SearchResult:
        """解析用户视频列表结果"""
        return SearchResult(
            id=item.get("bvid", ""),
            title=item.get("title", ""),
            desc=item.get("description", ""),
            author=item.get("author", ""),
            author_id=user_id,
            cover=item.get("pic", ""),
            url=f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            platform="bili",
            type="video",
            likes=item.get("like", 0),
            comments=item.get("review", 0),
            views=item.get("play", 0),
            create_time=str(item.get("created", "")),
            raw_data=item,
        )
    
    def _empty_detail(self, item_id: str) -> NoteDetail:
        """返回空的详情"""
        return NoteDetail(
            id=item_id,
            title="",
            desc="",
            author="",
            author_id="",
            platform="bili",
            type="video",
        )
    
    # =========================================================================
    # WBI 签名（需要 Patchright 模式获取 localStorage）
    # =========================================================================
    
    async def _sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        WBI 参数签名
        在 API 模式下，需要预先获取 wbi keys
        在 Patchright 模式下，可以直接从 localStorage 读取
        """
        if self.config.mode == ClientMode.PATCHRIGHT:
            # 从浏览器 localStorage 获取
            keys = await self._get_wbi_keys_from_browser()
        else:
            # 从 API 获取（需要登录）
            keys = await self._get_wbi_keys_from_api()
        
        if keys:
            signer = BilibiliSign(keys[0], keys[1])
            params = signer.sign(params)
        
        return params
    
    async def _get_wbi_keys_from_browser(self) -> Optional[tuple]:
        """从浏览器 localStorage 获取 wbi keys"""
        if not self._patchright_page:
            return None
        
        try:
            local_storage = await self._patchright_page.evaluate("() => window.localStorage")
            wbi_img_urls = local_storage.get("wbi_img_urls", "")
            
            if wbi_img_urls and "-" in wbi_img_urls:
                img_url, sub_url = wbi_img_urls.split("-")
                img_key = img_url.rsplit('/', 1)[1].split('.')[0]
                sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
                return (img_key, sub_key)
        except Exception as e:
            self._log(f"Get wbi keys from browser error: {e}", "warning")
        
        return None
    
    async def _get_wbi_keys_from_api(self) -> Optional[tuple]:
        """从 API 获取 wbi keys"""
        if self._wbi_keys:
            return self._wbi_keys
        
        try:
            url = f"{BASE_URL}/x/web-interface/nav"
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                wbi_img = response.get("data", {}).get("wbi_img", {})
                img_url = wbi_img.get("img_url", "")
                sub_url = wbi_img.get("sub_url", "")
                
                img_key = img_url.rsplit('/', 1)[1].split('.')[0]
                sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
                
                self._wbi_keys = (img_key, sub_key)
                return self._wbi_keys
        except Exception as e:
            self._log(f"Get wbi keys from API error: {e}", "warning")
        
        return None
