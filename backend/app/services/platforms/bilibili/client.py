"""
YLCraft — B站平台客户端
支持 API 模式和 Patchright 模式切换
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import string
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
    SEARCH_ALL,
    SEARCH_VIDEO,
    SEARCH_USER,
    SEARCH_TYPE_MAP,
    VIDEO_DETAIL,
    VIDEO_PLAYER,
    USER_INFO,
    USER_VIDEOS,
    COMMENTS,
    ORDER_TYPE_MAP,
    WBI_KEY_URL,
)

logger = logging.getLogger("ylcraft.platforms.bilibili")


# =============================================================================
# B站签名工具（WBI 签名）
# =============================================================================

class BilibiliSign:
    """B站 WBI 签名工具"""
    
    # WBI 签名用到的 mixin key 加密字典
    MIXIN_KEY_ENC_TAB = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
        33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
        61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57,
        62, 11, 36, 20, 34, 44, 52,
    ]
    
    def __init__(self, img_key: str, sub_key: str):
        self.img_key = img_key
        self.sub_key = sub_key
    
    @staticmethod
    def get_mixin_key(orig: str) -> str:
        """对原始 key 进行混淆加密"""
        return ''.join([orig[i] for i in BilibiliSign.MIXIN_KEY_ENC_TAB])[:32]
    
    def sign(self, params: Dict[str, Any]) -> str:
        """对参数进行 WBI 签名，返回签名后的查询字符串
        
        参照 Bilibili 官方 WBI 签名算法：
        https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign-wbi.md
        """
        import hashlib
        import time
        import urllib.parse
        
        # 复制参数，避免修改原字典
        params = dict(params)
        
        # 添加时间戳（参与排序和签名）
        params['wts'] = int(time.time())
        
        # 按 key 排序
        sorted_params = sorted(params.items())
        
        # URL 编码
        encoded = urllib.parse.urlencode(sorted_params)
        
        # B站要求：不编码 !'()*-._~ 这些字符
        # urllib.parse.urlencode 会编码 !'()~，需要手动还原
        encoded = encoded.replace('%21', '!')   # !
        encoded = encoded.replace('%27', "'")   # '
        encoded = encoded.replace('%28', '(')   # (
        encoded = encoded.replace('%29', ')')   # )
        encoded = encoded.replace('%7E', '~')   # ~
        # *-._ 不会被 urlencode 编码，无需处理
        
        # 计算 w_rid = md5(encoded + mixin_key)
        mixin_key = self.get_mixin_key(self.img_key + self.sub_key)
        w_rid = hashlib.md5((encoded + mixin_key).encode('utf-8')).hexdigest()
        
        # 返回完整的查询字符串（w_rid 单独附加，不参与签名）
        return f"{encoded}&w_rid={w_rid}"


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
    
    async def _get_wbi_keys(self) -> tuple[str, str]:
        """
        获取 WBI keys（用于签名）
        从 B站 API 获取 img_key 和 sub_key
        即使未登录（code=-101），data 中可能仍有 wbi_img
        """
        if self._wbi_keys:
            return self._wbi_keys

        url = f"{BASE_URL}{WBI_KEY_URL}"
        logger.debug(f"[bili] Getting WBI keys from {url}")

        response = await self.request("GET", url)

        if not isinstance(response, dict):
            raise RuntimeError(f"[bili] WBI keys: unexpected response type: {type(response)}")

        data = response.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"[bili] WBI keys: no data in response, code={response.get('code')}, msg={response.get('message')}")

        wbi_img = data.get("wbi_img")
        if not isinstance(wbi_img, dict):
            raise RuntimeError(f"[bili] WBI keys: no wbi_img in data")

        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")

        img_match = re.search(r'/([^/]+)\.png', img_url) if img_url else None
        sub_match = re.search(r'/([^/]+)\.png', sub_url) if sub_url else None

        if not img_match or not sub_match:
            raise RuntimeError(f"[bili] WBI keys: failed to extract keys from URLs: img_url={img_url}, sub_url={sub_url}")

        self._wbi_keys = (img_match.group(1), sub_match.group(1))
        logger.info(f"[bili] Got WBI keys: img={self._wbi_keys[0][:8]}..., sub={self._wbi_keys[1][:8]}...")
        return self._wbi_keys

    async def _sign_params(self, params: Dict[str, Any]) -> str:
        """
        对参数进行 WBI 签名，返回签名后的查询字符串
        """
        img_key, sub_key = await self._get_wbi_keys()
        signer = BilibiliSign(img_key, sub_key)
        return signer.sign(params)
    
    # =========================================================================
    # 实现抽象方法
    # =========================================================================
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头（API 模式用）"""
        headers = {
            "User-Agent": self._get_default_user_agent(),
            "Referer": "https://search.bilibili.com",
            "Origin": "https://search.bilibili.com",
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
        支持类型：video（视频）、user（用户）、article（专栏）、bangumi（番剧）、movie（影视）、live（直播）
        
        重要：视频搜索统一用 search_videos()，因为它支持排序 + 日期筛选
        """
        search_type_str = params.search_type.value if hasattr(params.search_type, 'value') else str(params.search_type)
        
        if search_type_str == 'user':
            return await self.search_users(params.keyword, params.max_results, params.sort_by, params.page)
        elif search_type_str == 'article':
            return await self.search_articles(params.keyword, params.max_results, params.sort_by, params.page)
        elif search_type_str == 'bangumi':
            return await self.search_bangumi(params.keyword, params.max_results, params.sort_by, params.page)
        elif search_type_str == 'movie':
            return await self.search_movie(params.keyword, params.max_results, params.sort_by, params.page)
        elif search_type_str == 'live':
            return await self.search_live(params.keyword, params.max_results, params.sort_by, params.page)
        elif search_type_str == 'video':
            # 视频搜索：统一用 search_videos()，支持排序 + 日期筛选
            return await self.search_videos(
                keyword=params.keyword,
                max_results=params.max_results,
                order=params.sort_by or "totalrank",
                page=params.page,
                **params.extra,
            )
        else:
            # 其他类型（包括旧的 'note' 值）：也用 search_videos()
            logger.warning(f"[bili] Unknown search_type '{search_type_str}', fallback to video search")
            return await self.search_videos(
                keyword=params.keyword,
                max_results=params.max_results,
                order=params.sort_by or "totalrank",
                **params.extra,
            )
    

    def _generate_qv_id(self) -> str:
        """生成 qv_id（32位随机字符串）"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=32))

    def _parse_date_filter(self, date_value: str) -> Optional[int]:
        """
        将相对日期值转换为 pubtime_begin_s 时间戳
        date_value: '1d'/'1w'/'1m'/'3m'/'6m'/'1y' 或直接的 Unix 时间戳字符串
        返回: Unix 时间戳（秒）或 None
        
        使用自然日计算（今天 00:00:00 到 23:59:59）
        """
        if not date_value:
            return None
        
        # 如果已经是数字（直接的时间戳），直接返回
        if date_value.isdigit():
            return int(date_value)
        
        # 解析相对时间（自然日计算）
        import re
        from datetime import datetime, timedelta
        
        match = re.match(r'^(\d+)([dwmy])$', date_value.lower())
        if not match:
            return None
        
        num = int(match.group(1))
        unit = match.group(2)
        
        now = datetime.now()
        
        if unit == 'd':
            # 最近 N 天
            if num == 1:
                # "最近一天" = 今天凌晨 00:00 到现在
                begin = now.replace(hour=0, minute=0, second=0)
            else:
                begin = (now - timedelta(days=num)).replace(hour=0, minute=0, second=0)
            end = now.replace(hour=23, minute=59, second=59)
        elif unit == 'w':
            # 最近 N 周
            begin = (now - timedelta(weeks=num)).replace(hour=0, minute=0, second=0)
            end = now.replace(hour=23, minute=59, second=59)
        elif unit == 'm':
            # 最近 N 月（按 30 天算）
            begin = (now - timedelta(days=30*num)).replace(hour=0, minute=0, second=0)
            end = now.replace(hour=23, minute=59, second=59)
        elif unit == 'y':
            # 最近一年
            begin = (now - timedelta(days=365*num)).replace(hour=0, minute=0, second=0)
            end = now.replace(hour=23, minute=59, second=59)
        else:
            return None
        
        result_begin = int(begin.timestamp())
        result_end = int(end.timestamp())
        logger.debug(f"[bili] _parse_date_filter('{date_value}') = begin={result_begin}, end={result_end}")
        return result_begin

    async def search_all(
        self,
        keyword: str,
        max_results: int = 20,
        order: str = "totalrank",
        **kwargs,
    ) -> List[SearchResult]:
        """
        综合搜索（全部类型）
        使用 /x/web-interface/wbi/search/all/v2
        返回视频、专栏、用户等混合结果
        """
        logger.debug(f"[bili] Search all: keyword={keyword}, order={order}, kwargs={kwargs}")

        # 先处理日期筛选（在 params 定义之前计算时间戳）
        date_begin_s = None
        if 'date' in kwargs and kwargs['date']:
            date_begin_s = self._parse_date_filter(kwargs['date'])
            # 移除 date 参数，避免被当成 API 参数传递
            kwargs.pop('date', None)

        params = {
            "keyword": keyword,
            "page": 1,
            "page_size": min(max_results, 50),
            # 综合搜索不支持 order 参数，去掉
            "duration": kwargs.get('duration', 0),
            "from_source": "",
            "from_spmid": "333.337",
            "platform": "pc",
            "highlight": 1,
            "single_column": 0,
            "qv_id": self._generate_qv_id(),
            "web_location": 1430654,
        }

        # 添加额外的过滤参数（pubtime_begin_s, pubtime_end_s 等）
        for key in ['pubtime_begin_s', 'pubtime_end_s']:
            if key in kwargs and kwargs[key]:
                params[key] = kwargs[key]

        # 如果通过 date 筛选计算了时间戳，覆盖上面的值
        if date_begin_s:
            params['pubtime_begin_s'] = date_begin_s
            params['pubtime_end_s'] = int(time.time())

        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_ALL}?{query_string}"
        logger.debug(f"[bili] Search all URL: {url[:200]}...")

        response = await self.request("GET", url)

        if not isinstance(response, dict):
            logger.error(f"[bili] Search all unexpected response type: {type(response)}")
            return []

        code = response.get("code", -1)
        if code != 0:
            msg = response.get("message", response.get("msg", f"code={code}"))
            logger.warning(f"[bili] Search all failed: {msg}")
            return []

        data = response.get("data", {})
        # /wbi/search/all/v2 返回结构：data.result 是分组列表
        # 每个元素：{"result_type": "video", "data": [实际结果.]}
        result_groups = data.get("result", [])
        logger.debug(f"[bili] Search all got {len(result_groups)} result groups")

        results = []
        for group in result_groups:
            result_type = group.get("result_type", "")
            items = group.get("data", [])
            logger.debug(f"[bili] Group {result_type}: {len(items)} items")

            for item in items:
                if result_type == "video":
                    results.append(self._parse_video_result(item))
                elif result_type == "article":
                    results.append(self._parse_article_result(item))
                else:
                    # 其他类型暂时跳过
                    continue
                if len(results) >= max_results:
                    return results

        return results

    async def search_videos(
        self,
        keyword: str,
        max_results: int = 20,
        order: str = "totalrank",
        page: int = 1,
        **kwargs,
    ) -> List[SearchResult]:
        """
        搜索视频
        使用 WBI 签名的搜索 API
        支持额外参数：duration, pubtime_begin_s, pubtime_end_s 等
        """
        logger.debug(f"[bili] Search videos: keyword={keyword}, max_results={max_results}, order={order}, page={page}, kwargs={kwargs}")

        # max_results 作为每页数量（page_size），不再限制总数
        page_size = min(max_results, 50)

        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order": order or "totalrank",  # B站 API 用 order 参数，直接传字符串
            "duration": kwargs.get('duration', 0),
            "from_source": "",
            "from_spmid": "333.337",
            "platform": "pc",
            "highlight": 1,
            "single_column": 0,
            "qv_id": self._generate_qv_id(),
            "web_location": 1430654,
        }

        # 处理日期筛选（将相对值转换为 Unix 时间戳）
        if 'date' in kwargs and kwargs['date']:
            date_seconds = self._parse_date_filter(kwargs['date'])
            if date_seconds:
                params['pubtime_begin_s'] = date_seconds
                params['pubtime_end_s'] = int(time.time())
            # 移除 date 参数，避免被当成 API 参数传递
            kwargs.pop('date', None)

        # 添加额外的过滤参数（pubtime_begin_s, pubtime_end_s 等）
        for key in ['pubtime_begin_s', 'pubtime_end_s']:
            if key in kwargs and kwargs[key]:
                params[key] = kwargs[key]

        self._log(f"[bili] Search {params['search_type']}: keyword={keyword}, page={page}, page_size={page_size}")
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_VIDEO}?{query_string}"
        self._log(f"[bili] Search URL (first 150 chars): {url[:150]}...")
        logger.debug(f"[bili] Search URL: {url[:200]}...")

        response = await self.request("GET", url)

        if not isinstance(response, dict):
            logger.error(f"[bili] Search unexpected response type: {type(response)}")
            return []

        code = response.get("code", -1)
        if code != 0:
            msg = response.get("message", response.get("msg", f"code={code}"))
            logger.warning(f"[bili] Search failed: {msg}")
            return []

        data = response.get("data", {})
        result_list = data.get("result", [])
        total = data.get("numResults", 0) or data.get("numPages", 0) * page_size
        logger.debug(f"[bili] Search got {len(result_list)} results, total={total}")

        results = []
        for item in result_list:
            results.append(self._parse_video_result(item))

        # 把总条数存入第一个结果的 raw_data，供上层读取
        if results and total:
            results[0].raw_data["_total"] = total

        return results

    async def search_users(
        self,
        keyword: str,
        max_results: int = 20,
        sort_by: str = 'default',
        page: int = 1,
    ) -> List[SearchResult]:
        """搜索用户"""
        self._log(f"Searching users: {keyword}, page={page}")
        
        params = {
            "search_type": "bili_user",
            "keyword": keyword,
            "page": page,
            "page_size": min(max_results, 50),
        }
        
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_USER}?{query_string}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_list = data.get("result", [])
                total = data.get("numResults", 0) or data.get("numPages", 0) * min(max_results, 50)
                self._log(f"User search got {len(result_list)} results, total={total}")
                
                results = []
                for item in result_list:
                    results.append(self._parse_user_result(item))
                
                # 把总条数存入第一个结果的 raw_data，供上层读取
                if results and total:
                    results[0].raw_data["_total"] = total
                
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
        sort_by: str = 'totalrank',
        page: int = 1,
    ) -> List[SearchResult]:
        """搜索专栏文章"""
        self._log(f"Searching articles: {keyword}, page={page}")
        
        # 专栏排序映射
        article_order_map = {
            'totalrank': 0,  # 综合
            'pubdate': 1,    # 最新发布
            'click': 2,      # 最多点击
            'likes': 3,      # 最多喜欢
            'reply': 4,      # 最多评论
        }
        
        page_size = min(max_results, 50)
        params = {
            "search_type": "article",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order_type": article_order_map.get(sort_by, 0),
        }
        
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_ARTICLE}?{query_string}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_list = data.get("result", [])
                total = data.get("numResults", 0) or data.get("numPages", 0) * page_size
                self._log(f"Article search got {len(result_list)} results, total={total}")
                
                results = []
                for item in result_list:
                    results.append(self._parse_article_result(item))
                
                # 把总条数存入第一个结果的 raw_data，供上层读取
                if results and total:
                    results[0].raw_data["_total"] = total
                
                return results
            else:
                return []
                
        except Exception as e:
            self._log(f"Search articles error: {e}", "error")
            return []
    
    async def search_bangumi(
        self,
        keyword: str,
        max_results: int = 20,
        sort_by: str = 'totalrank',
        page: int = 1,
    ) -> List[SearchResult]:
        """搜索番剧"""
        self._log(f"Searching bangumi: {keyword}, page={page}")
        
        page_size = min(max_results, 50)
        params = {
            "search_type": "media_bangumi",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order_type": ORDER_TYPE_MAP.get(sort_by, 0),
        }
        
        self._log(f"[bili] Search {params['search_type']}: keyword={keyword}, page={page}, page_size={page_size}")
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_VIDEO}?{query_string}"
        self._log(f"[bili] Search URL (first 200 chars): {url[:200]}...")
        print(f"[DEBUG] Bangumi URL: {url[:200]}...")
        
        try:
            response = await self.request("GET", url)
            print(f"[DEBUG] Bangumi response type: {type(response)}")
            
            if isinstance(response, dict):
                code = response.get("code", -1)
                print(f"[DEBUG] Bangumi response code: {code}, message: {response.get('message', response.get('msg', ''))}")
                
                if code == 0:
                    data = response.get("data", {})
                    result_list = data.get("result", [])
                    total = data.get("numResults", 0) or data.get("numPages", 0) * page_size
                    self._log(f"Bangumi search got {len(result_list)} results, total={total}")
                    print(f"[DEBUG] Bangumi results: {len(result_list)}, total={total}")
                    
                    results = []
                    for item in result_list:
                        results.append(self._parse_bangumi_result(item))
                    
                    # 把总条数存入第一个结果的 raw_data，供上层读取
                    if results and total:
                        results[0].raw_data["_total"] = total
                        print(f"[DEBUG] First result title: {results[0].title}")
                    
                    return results
                else:
                    msg = response.get("message", response.get("msg", f"code={code}"))
                    self._log(f"Search bangumi failed: {msg}", "warning")
                    print(f"[DEBUG] Bangumi search failed: {msg}")
                    return []
            else:
                self._log(f"Search bangumi unexpected response type: {type(response)}", "error")
                print(f"[DEBUG] Unexpected response type: {type(response)}")
                return []
                
        except Exception as e:
            self._log(f"Search bangumi error: {e}", "error")
            print(f"[DEBUG] Exception: {e}")
            return []
    
    async def search_movie(
        self,
        keyword: str,
        max_results: int = 20,
        sort_by: str = 'totalrank',
        page: int = 1,
    ) -> List[SearchResult]:
        """搜索影视"""
        self._log(f"Searching movie: {keyword}, page={page}")
        
        page_size = min(max_results, 50)
        params = {
            "search_type": "media_ft",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order_type": ORDER_TYPE_MAP.get(sort_by, 0),
        }
        
        self._log(f"[bili] Search {params['search_type']}: keyword={keyword}, page={page}, page_size={page_size}")
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_VIDEO}?{query_string}"
        self._log(f"[bili] Search URL (first 150 chars): {url[:150]}...")
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_list = data.get("result", [])
                total = data.get("numResults", 0) or data.get("numPages", 0) * page_size
                self._log(f"Movie search got {len(result_list)} results, total={total}")
                
                results = []
                for item in result_list:
                    results.append(self._parse_movie_result(item))
                
                # 把总条数存入第一个结果的 raw_data，供上层读取
                if results and total:
                    results[0].raw_data["_total"] = total
                
                return results
            else:
                return []
                
        except Exception as e:
            self._log(f"Search movie error: {e}", "error")
            return []
    
    async def search_live(
        self,
        keyword: str,
        max_results: int = 20,
        sort_by: str = 'default',
        page: int = 1,
    ) -> List[SearchResult]:
        """搜索直播"""
        self._log(f"Searching live: {keyword}, page={page}")
        
        page_size = min(max_results, 50)
        params = {
            "search_type": "live",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
        }
        
        self._log(f"[bili] Search {params['search_type']}: keyword={keyword}, page={page}, page_size={page_size}")
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_VIDEO}?{query_string}"
        self._log(f"[bili] Search URL (first 150 chars): {url[:150]}...")
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_list = data.get("result", [])
                total = data.get("numResults", 0) or data.get("numPages", 0) * page_size
                self._log(f"Live search got {len(result_list)} results, total={total}")
                
                results = []
                for item in result_list:
                    results.append(self._parse_live_result(item))
                
                # 把总条数存入第一个结果的 raw_data，供上层读取
                if results and total:
                    results[0].raw_data["_total"] = total
                
                return results
            else:
                return []
                
        except Exception as e:
            self._log(f"Search live error: {e}", "error")
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
        """解析视频搜索结果（去除 HTML 标签，修复封面 URL）"""
        import re
        raw_title = item.get("title", "")
        raw_desc = item.get("description", "")
        # 去除 B站返回的 <em class="keyword"> 等 HTML 标签
        title = re.sub(r'<[^>]+>', '', raw_title)
        desc = re.sub(r'<[^>]+>', '', raw_desc)

        # 修复封面 URL（B站返回协议相对 URL，需要补 https:）
        pic = item.get("pic", "")
        if pic.startswith("//"):
            cover = "https:" + pic
        else:
            cover = pic

        return SearchResult(
            id=item.get("bvid", ""),
            title=title,
            desc=desc,
            author=item.get("author", ""),
            author_id=str(item.get("mid", "")),
            cover=cover,
            url=f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            platform="bili",
            type="video",
            likes=item.get("like", 0),
            comments=item.get("review", 0),
            shares=0,
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
    
    def _parse_bangumi_result(self, item: Dict) -> SearchResult:
        """解析番剧搜索结果"""
        return SearchResult(
            id=str(item.get("season_id", "")),
            title=item.get("title", ""),
            desc=item.get("styles", ""),
            author="",
            author_id="",
            cover=item.get("cover", ""),
            url=item.get("url", ""),
            platform="bili",
            type="bangumi",
            likes=item.get("rating", {}).get("score", 0),
            views=item.get("view", 0),
            raw_data=item,
        )
    
    def _parse_movie_result(self, item: Dict) -> SearchResult:
        """解析影视搜索结果"""
        return SearchResult(
            id=str(item.get("season_id", "")),
            title=item.get("title", ""),
            desc=item.get("styles", ""),
            author="",
            author_id="",
            cover=item.get("cover", ""),
            url=item.get("url", ""),
            platform="bili",
            type="movie",
            likes=item.get("rating", {}).get("score", 0),
            views=item.get("view", 0),
            raw_data=item,
        )
    
    def _parse_live_result(self, item: Dict) -> SearchResult:
        """解析直播搜索结果"""
        return SearchResult(
            id=str(item.get("roomid", "")),
            title=item.get("title", ""),
            desc=item.get("area", ""),
            author=item.get("uname", ""),
            author_id=str(item.get("uid", "")),
            cover=item.get("cover", ""),
            url=f"https://live.bilibili.com/{item.get('roomid', '')}",
            platform="bili",
            type="live",
            views=item.get("online", 0),
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
