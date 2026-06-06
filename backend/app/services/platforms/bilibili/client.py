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
    SEARCH_ARTICLE,
    SEARCH_USER,
    SEARCH_TYPE_MAP,
    VIDEO_DETAIL,
    VIDEO_PLAYER,
    USER_INFO,
    USER_VIDEOS,
    USER_SERIES,
    COMMENTS,
    ORDER_TYPE_MAP,
    WBI_KEY_URL,
    FAV_LIST,
    FAV_RESOURCE_LIST,
    FAV_INFO,
    HISTORY_CURSOR,
    HISTORY_SEARCH,
    FOLLOWINGS,
    PAID_COURSES,
    PAID_COURSE_DETAIL,
    PAID_COURSE_PLAYURL,
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
            "Referer": "https://space.bilibili.com/",  # 修正：空间相关API需要此referer
            "Origin": "https://space.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
        }

        if self.config.cookie:
            headers["Cookie"] = self.config.cookie
            self._log(f"_build_headers: Cookie set, len={len(self.config.cookie)}, preview={self.config.cookie[:80]!r}", "debug")
        else:
            self._log(f"_build_headers: No cookie available!", "warning")

        return headers
    
    def _get_default_user_agent(self) -> str:
        """获取默认 User-Agent"""
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    def _extract_user_id_from_cookie(self) -> int:
        """从 Cookie 中提取用户 ID（DedeUserID）
        
        Returns:
            用户ID，如果提取失败返回 0
        """
        if not self.config.cookie:
            return 0
        
        try:
            # 从 Cookie 字符串中查找 DedeUserID
            cookie_str = self.config.cookie
            # 匹配 DedeUserID=xxx 模式
            import re
            match = re.search(r'DedeUserID=(\d+)', cookie_str)
            if match:
                return int(match.group(1))
        except Exception as e:
            self._log(f"Failed to extract user ID from cookie: {e}", "warning")
        
        return 0
    
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
            # 从 extra 中取 order_sort（前端传来的排序方向）
            order_sort = params.extra.get('order_sort', 0) if params.extra else 0
            return await self.search_users(
                keyword=params.keyword,
                max_results=params.max_results,
                sort_by=params.sort_by,
                order_sort=order_sort,
                page=params.page,
            )
        elif search_type_str == 'article':
            return await self.search_articles(
                keyword=params.keyword,
                max_results=params.max_results,
                sort_by=params.sort_by,
                page=params.page,
            )
        elif search_type_str == 'bangumi':
            return await self.search_bangumi(
                keyword=params.keyword,
                max_results=params.max_results,
                sort_by=params.sort_by,
                page=params.page,
            )
        elif search_type_str == 'movie':
            return await self.search_movie(
                keyword=params.keyword,
                max_results=params.max_results,
                sort_by=params.sort_by,
                page=params.page,
            )
        elif search_type_str == 'live':
            return await self.search_live(
                keyword=params.keyword,
                max_results=params.max_results,
                sort_by=params.sort_by,
                page=params.page,
            )
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
                page=params.page,
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
        order_sort: int = 0,  # 0=高到低，1=低到高
        page: int = 1,
    ) -> List[SearchResult]:
        """搜索用户"""
        self._log(f"Searching users: {keyword}, page={page}, sort_by={sort_by}, order_sort={order_sort}")
        
        # 用户搜索排序映射（order 参数）
        user_order_map = {
            'default': '',       # 综合排序，不传 order
            'fans': 'fans',     # 粉丝排序
            'level': 'level',    # 等级排序
        }
        
        params = {
            "search_type": "bili_user",
            "keyword": keyword,
            "page": page,
            "page_size": min(max_results, 50),
            "from_spmid": "333.337",
            "platform": "pc",
            "highlight": 1,
            "single_column": 0,
            "web_location": 1430654,
            "source_tag": 3,
        }
        
        # 添加 order / order_sort 参数
        order_value = user_order_map.get(sort_by, '')
        if order_value:
            params["order"] = order_value
            params["order_sort"] = order_sort
        
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
        
        # 专栏排序映射（API 用 order 参数，传字符串值）
        # 注意：B站专栏 API 的 order 值比较特殊
        article_order_map = {
            'totalrank': 'totalrank',  # 综合排序
            'pubdate': 'pubdate',      # 最新发布
            'click': 'click',          # 最多点击
            'likes': 'attention',      # 最多喜欢（不是 likes！）
            'reply': 'scores',         # 最多评论（不是 reply！）
            'stow': 'stow',           # 最多收藏
            'share': 'share',          # 最多分享
        }
        
        page_size = min(max_results, 50)
        params = {
            "search_type": "article",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order": article_order_map.get(sort_by, 'totalrank'),
            "category_id": 0,
            "platform": "pc",
            "highlight": 1,
            "single_column": 0,
            "from_spmid": "333.337",
            "web_location": 1430654,
            "source_tag": 3,
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
        sort_by: str = 'online',
        page: int = 1,
    ) -> List[SearchResult]:
        """搜索直播
        
        sort_by:
        - 'online': 直播间按人气排序
        - 'live_time': 直播间按开播时间排序
        - 'anchor': 搜索主播用户
        """
        self._log(f"Searching live: {keyword}, page={page}, sort_by={sort_by}")
        
        page_size = min(max_results, 50)
        
        # 主播搜索：使用独立的 API
        if sort_by == 'anchor':
            params = {
                "search_type": "live_user",
                "keyword": keyword,
                "page": page,
                "page_size": page_size,
            }
            
            self._log(f"[bili] Search live_user: keyword={keyword}, page={page}, page_size={page_size}")
            query_string = await self._sign_params(params)
            url = f"{BASE_URL}{SEARCH_VIDEO}?{query_string}"
            
            try:
                response = await self.request("GET", url)
                
                if isinstance(response, dict) and response.get("code") == 0:
                    data = response.get("data", {})
                    result_list = data.get("result", [])
                    
                    # search_type=live_user 返回 data.result 是 flat array
                    if isinstance(result_list, dict):
                        # 防御性处理：如果返回的是对象格式（旧格式），按原方式解析
                        result_list = result_list.get("live_user", [])
                    
                    total = data.get("numResults", 0) or data.get("numPages", 0) * page_size
                    self._log(f"Live user search got {len(result_list)} results, total={total}")
                    
                    results = []
                    for item in result_list:
                        results.append(self._parse_live_user_result(item))
                    
                    if results and total:
                        results[0].raw_data["_total"] = total
                    
                    return results
                else:
                    msg = response.get("message", "Unknown error") if isinstance(response, dict) else "Request failed"
                    self._log(f"Search live_user failed: {msg}", "warning")
                    return []
                    
            except Exception as e:
                self._log(f"Search live_user error: {e}", "error")
                return []
        
        # 直播间搜索：支持 order 参数
        order_map = {
            'live_time': 'live_time',
            'online': 'online',
        }
        order = order_map.get(sort_by, 'online')
        
        params = {
            "search_type": "live",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order": order,
        }
        
        self._log(f"[bili] Search live: keyword={keyword}, page={page}, order={order}")
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{SEARCH_VIDEO}?{query_string}"
        
        try:
            response = await self.request("GET", url)
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                result_obj = data.get("result", {})
                
                # search_type=live 返回 data.result 是对象 {"live_room": [...]}
                # 防御性处理：如果是 list 则按旧逻辑兼容
                if isinstance(result_obj, dict):
                    result_list = result_obj.get("live_room", [])
                elif isinstance(result_obj, list):
                    result_list = result_obj
                else:
                    result_list = []
                
                # 总数：优先从 pageinfo 取，没有则从 data 顶层取
                pageinfo = data.get("pageinfo", {})
                total = pageinfo.get("live_room", {}).get("numResults", 0)
                if not total:
                    total = data.get("numResults", 0) or data.get("numPages", 0) * page_size
                
                self._log(f"Live room search got {len(result_list)} results, total={total}")
                
                results = []
                for item in result_list:
                    results.append(self._parse_live_result(item))
                
                if results and total:
                    results[0].raw_data["_total"] = total
                
                return results
            else:
                msg = response.get("message", "Unknown error") if isinstance(response, dict) else "Request failed"
                self._log(f"Search live failed: {msg}", "warning")
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
        
        # 添加 WBI 签名（必须启用才能获取高清画质）
        query_string = await self._sign_params(params)
        
        url = f"{BASE_URL}{VIDEO_PLAYER}?{query_string}"
        
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
    
    async def get_video_play_info(self, bvid: str) -> dict:
        """
        获取视频完整播放信息（DASH格式，含多清晰度 + 音频）
        
        返回 dict: {
            "dash": {
                "video": [{"id": 127, "baseUrl": "...", "width": 1920, "height": 1080}],
                "audio": [{"baseUrl": "..."}]
            }
        }
        
        策略：优先使用 UGC API（x/player/playurl），适用于所有视频类型。
        只有确认是真正的 PGC 内容（官方番剧/动漫）且 UGC API 不可用时，
        才使用 PGC 专用 API（pgc/player/web/playurl）。
        
        注意：用户"合集"（UGC collection）也有 season_id，但绝非 PGC 内容，
        必须使用 UGC API。
        """
        self._log(f"Getting video play info: {bvid}")
        
        # 先获取视频基础信息
        view_url = f"{BASE_URL}{VIDEO_DETAIL}?{urlencode({'bvid': bvid})}"
        try:
            view_resp = await self.request("GET", view_url)
            view_data = view_resp.get("data", {}) if isinstance(view_resp, dict) else {}
        except Exception:
            view_data = {}
        
        season_id = view_data.get("season_id")
        aid = view_data.get("aid")
        cid = view_data.get("cid")
        
        # 判断是否为真正的 PGC 内容（而非 UGC 合集）
        # 真正的 PGC 内容特征：redirect_url 指向 bangumi，或 rights 中有 PGC 标记
        is_true_pgc = False
        if season_id:
            redirect_url = view_data.get("redirect_url", "")
            if redirect_url and "bangumi" in redirect_url:
                is_true_pgc = True
            elif view_data.get("rights", {}).get("is_pgc"):
                is_true_pgc = True
        
        # ═══════════════════════════════════════════════════════════════
        # Step 1: 始终优先使用 UGC API（适用所有 UGC + 合集视频）
        # ═══════════════════════════════════════════════════════════════
        ugc_params = {
            "bvid": bvid,
            "qn": 127,
            "fnval": 4048,        # 更现代的格式值（支持 8K/HDR/杜比）
            "fnver": 0,
            "fourk": 1,
            "platform": "web",    # 必须参数
            "high_level": 1,      # 高清画质标识
        }
        # cid 是可选的，但某些视频需要
        if cid:
            ugc_params["cid"] = cid
        ugc_query = await self._sign_params(ugc_params)
        ugc_play_url = f"{BASE_URL}{VIDEO_PLAYER}?{ugc_query}"
        
        try:
            ugc_resp = await self.request("GET", ugc_play_url)
            if isinstance(ugc_resp, dict) and ugc_resp.get("code") == 0:
                data = ugc_resp.get("data", {})
                if data.get("dash") or data.get("durl"):
                    self._log(f"UGC API success: got {len(data.get('dash', {}).get('video', []))} video streams")
                    return data
                self._log(f"UGC API returned empty play data", "warning")
            else:
                err_msg = ugc_resp.get("message", "") if isinstance(ugc_resp, dict) else ""
                err_code = ugc_resp.get("code", 0) if isinstance(ugc_resp, dict) else 0
                self._log(f"UGC API failed: code={err_code}, msg={err_msg}", "warning")
        except Exception as e:
            self._log(f"UGC API error: {e}", "warning")
        
        # ═══════════════════════════════════════════════════════════════
        # Step 2: 只有真正的 PGC 内容才尝试 PGC 专用 API
        # ═══════════════════════════════════════════════════════════════
        if is_true_pgc and season_id and aid and cid:
            self._log(f"True PGC video (season_id={season_id}), trying PGC playurl API")
            pgc_params = {
                "aid": aid,
                "cid": cid,
                "qn": 127,
                "fnval": 4048,
                "fnver": 0,
                "fourk": 1,
                "platform": "web",
            }
            pgc_query = await self._sign_params(pgc_params)
            pgc_play_url = f"{BASE_URL}/pgc/player/web/playurl?{pgc_query}"
            
            try:
                pgc_resp = await self.request("GET", pgc_play_url)
                if isinstance(pgc_resp, dict) and pgc_resp.get("code") == 0:
                    data = pgc_resp.get("data", {})
                    if data.get("dash") or data.get("durl"):
                        self._log(f"PGC API success")
                        return data
                    self._log(f"PGC API returned empty play data", "warning")
                else:
                    err_msg = pgc_resp.get("message", "") if isinstance(pgc_resp, dict) else ""
                    err_code = pgc_resp.get("code", 0) if isinstance(pgc_resp, dict) else 0
                    self._log(f"PGC API failed: code={err_code}, msg={err_msg}", "error")
            except Exception as e:
                self._log(f"PGC API error: {e}", "error")
        
        # ═══════════════════════════════════════════════════════════════
        # Step 3: 最后尝试不带 WBI 签名的 UGC API（兼容老接口）
        # ═══════════════════════════════════════════════════════════════
        self._log(f"Trying unsigned UGC API as last resort", "warning")
        fallback_params = {
            "bvid": bvid,
            "qn": 80,            # 降级到 1080P
            "fnval": 1,          # 基础格式
            "fnver": 0,
            "platform": "web",
            "wts": int(time.time()),  # 添加时间戳
        }
        if cid:
            fallback_params["cid"] = cid
        fallback_url = f"{BASE_URL}{VIDEO_PLAYER}?{urlencode(fallback_params)}"
        
        try:
            fb_resp = await self.request("GET", fallback_url)
            if isinstance(fb_resp, dict) and fb_resp.get("code") == 0:
                data = fb_resp.get("data", {})
                if data.get("dash") or data.get("durl"):
                    self._log(f"Unsigned UGC API success (degraded quality)")
                    return data
            else:
                err_msg = fb_resp.get("message", "") if isinstance(fb_resp, dict) else ""
                self._log(f"All play APIs failed. Final error: {err_msg}", "error")
        except Exception as e:
            self._log(f"All play APIs failed: {e}", "error")
        
        return {}
    
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
                
                # B站不同接口/版本，字段位置可能不同，做多层 fallback
                archive_count = (
                    card.get("archive_count")
                    or card.get("video")
                    or data.get("archive_count")
                    or 0
                )
                likes_count = (
                    stats.get("likes")
                    or card.get("likes")
                    or data.get("like_num")
                    or 0
                )
                
                return UserProfile(
                    id=str(card.get("mid", user_id)),
                    name=card.get("name", ""),
                    avatar=card.get("face", ""),
                    platform="bili",
                    followers=stats.get("follower") or card.get("fans", 0),
                    following=stats.get("following") or card.get("attention", 0),
                    total_likes=likes_count,
                    total_videos=archive_count,
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
        page: int = 1,
    ) -> Dict[str, Any]:
        """获取用户发布的视频列表
        
        Args:
            user_id: 用户ID
            max_results: 最大返回数量
            order: 排序方式
            page: 页码
            
        Returns:
            {"list": List[SearchResult], "total": int}
        """
        self._log(f"Getting user videos: {user_id}, page={page}, order={order}")
        
        params = {
            "mid": user_id,
            "ps": min(max_results, 50),
            "pn": page,
            "order": order,
            "tid": 0,
            "keyword": "",
            "index": 1,
            "order_avoided": "true",
            "platform": "web",
            "web_location": "333.1387",
            "dm_img_list": "[]",
            "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
            "dm_cover_img_str": "QU5HTEUgKE5WSURJQSwgTlZJRElBIEdlRm9yY2UgUlRYIDMwNjAgTGFwdG9wIEdQVSAoMHgwMDAwMjU2MCkgRGlyZWN0M0QxMSB2c181XzAgcHNfNV8wLCBEM0QxMSlHb29nbGUgSW5jLiAoTlZJRElBKQ",
            "dm_img_inter": '{"ds":[],"wh":[4182,2169,54],"of":[62,124,62]}',
        }
        
        query_string = await self._sign_params(params)
        url = f"{BASE_URL}{USER_VIDEOS}?{query_string}"
        
        try:
            response = await self.request("GET", url)
            self._log(f"User videos response: code={response.get('code')}, msg={response.get('message', '')}")
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                video_list = data.get("list", {}).get("vlist", [])
                total_count = data.get("page", {}).get("count", len(video_list))
                self._log(f"User videos: got {len(video_list)} items, total={total_count}")
                if len(video_list) > 0:
                    self._log(f"First video keys: {list(video_list[0].keys())[:10]}")
                
                results = []
                for item in video_list[:max_results]:
                    search_result = self._parse_user_video_result(item, user_id)
                    results.append(search_result)
                
                return {"list": results, "total": total_count}
            else:
                self._log(f"User videos failed: {response.get('message', 'unknown')}", "warning")
                return {"list": [], "total": 0}
                
        except Exception as e:
            self._log(f"Get user videos error: {e}", "error")
            return {"list": [], "total": 0}
    
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
    # 收藏夹相关（需要登录）
    # =========================================================================

    async def _get_current_user_mid(self) -> Optional[str]:
        """通过nav接口获取当前登录用户的mid"""
        try:
            url = f"{BASE_URL}{WBI_KEY_URL}"
            response = await self.request("GET", url)
            
            self._log(f"nav response type: {type(response)}, keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}", "debug")
            
            if isinstance(response, dict):
                self._log(f"nav response code: {response.get('code')}, data keys: {list(response.get('data', {}).keys())}")
                if response.get("code") == 0:
                    data = response.get("data", {})
                    # 尝试多种可能的字段名
                    mid = data.get("mid") or data.get("midStr") or data.get("uid")
                    if mid:
                        self._log(f"Got current user mid: {mid}")
                        return str(mid)
            self._log("Cannot find mid from nav response", "warning")
            return None
        except Exception as e:
            self._log(f"Get current user mid error: {e}", "error")
            return None
    
    async def get_favorite_list(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取收藏夹列表
        
        Args:
            user_id: 用户ID，如果不传则获取当前登录用户的收藏夹（需要cookie）
                    如果传了则获取该用户的公开收藏夹（不需要cookie）
        """
        if user_id:
            self._log(f"Getting public favorite list for user: {user_id}")
            params = {"up_mid": user_id, "pn": 1, "ps": 100, "web_location": "333.1387"}
        else:
            self._log(f"Getting my favorite list")
            if not self.config.cookie:
                self._log("No cookie, cannot get favorite list", "warning")
                return []
            
            # 获取当前登录用户的mid
            current_mid = await self._get_current_user_mid()
            if not current_mid:
                self._log("Cannot get current user mid", "warning")
                return []
            
            self._log(f"Current user mid: {current_mid}")
            params = {"up_mid": current_mid, "pn": 1, "ps": 100, "web_location": "333.1387"}
        
        try:
            # WBI 签名
            query_string = await self._sign_params(params)
            url = f"{BASE_URL}{FAV_LIST}?{query_string}"
            
            response = await self.request("GET", url)
            
            self._log(f"Favorite list API response keys: {list(response.keys()) if isinstance(response, dict) else type(response)}", "debug")
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                self._log(f"Favorite data keys: {list(data.keys())}", "debug")
                
                # 尝试多种可能的字段名
                favorites = data.get("list", []) or data.get("folders", []) or data.get("data", []) or []
                self._log(f"Got {len(favorites)} favorites", "debug")
                
                result = []
                for fav in favorites:
                    result.append({
                        "id": str(fav.get("id", "")),
                        "title": fav.get("title", ""),
                        "cover": self._fix_bili_url(fav.get("cover", "")),
                        "media_count": fav.get("media_count", 0) or fav.get("cnt", 0),
                        "ctime": fav.get("ctime", 0),
                        "mtime": fav.get("mtime", 0),
                        "fav_state": fav.get("fav_state", 0),
                    })
                
                self._log(f"Got {len(result)} favorites")
                return result
            else:
                code = response.get("code", -1)
                msg = response.get("message", "")
                self._log(f"Get favorite list failed: code={code}, msg={msg}", "warning")
                return []
                
        except Exception as e:
            self._log(f"Get favorite list error: {e}", "error")
            return []
    
    async def get_favorite_detail(self, media_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取收藏夹内的视频列表
        
        使用 web API /x/v3/fav/resource/list，需要 WBI 签名
        关键参数：platform=web 和 web_location=333.1387
        """
        self._log(f"Getting favorite detail: media_id={media_id}, page={page}")
        
        params = {
            "media_id": media_id,
            "pn": page,
            "ps": min(page_size, 50),
            "keyword": "",
            "order": "mtime",
            "type": 0,
            "tid": 0,
            "platform": "web",
            "web_location": "333.1387",
        }
        
        try:
            # WBI 签名
            query_string = await self._sign_params(params)
            url = f"{BASE_URL}{FAV_RESOURCE_LIST}?{query_string}"
            
            response = await self.request("GET", url)
            
            # 调试：打印原始响应
            raw = json.dumps(response, ensure_ascii=False)[:1000] if isinstance(response, dict) else str(response)[:500]
            self._log(f"Favorite detail raw response: {raw}", "debug")
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                items = data.get("medias", []) or []
                
                self._log(f"Got {len(items)} medias from favorite detail")
                
                result = []
                for item in items:
                    bvid = item.get("bvid", "") or item.get("bv_id", "")
                    result.append({
                        "id": bvid,
                        "title": item.get("title", ""),
                        "desc": item.get("intro", ""),
                        "cover": self._fix_bili_url(item.get("cover", "")),
                        "author": item.get("upper", {}).get("name", ""),
                        "author_id": str(item.get("upper", {}).get("mid", "")),
                        "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                        "duration": item.get("duration", 0),
                        "bv_id": bvid,
                        "pubdate": item.get("pubtime", 0) or item.get("pubdate", 0),
                        "ctime": item.get("ctime", 0),
                        "fav_time": item.get("fav_time", 0),
                        "stat": {
                            "view": item.get("cnt_info", {}).get("play", 0),
                            "like": item.get("cnt_info", {}).get("vt", 0),
                            "coin": item.get("cnt_info", {}).get("coin", 0),
                            "favorite": item.get("cnt_info", {}).get("collect", 0),
                            "reply": item.get("cnt_info", {}).get("reply", 0),
                        },
                    })
                
                # 获取总条数
                info = data.get("info", {})
                total = info.get("media_count", len(result))
                
                return {
                    "total": total,
                    "list": result,
                    "page": page,
                    "page_size": page_size,
                }
            else:
                code = response.get("code", -1) if isinstance(response, dict) else -1
                msg = response.get("message", "") if isinstance(response, dict) else str(response)[:200]
                self._log(f"Get favorite detail failed: code={code}, msg={msg}", "warning")
                return {"total": 0, "list": [], "page": page, "page_size": page_size}
                
        except Exception as e:
            self._log(f"Get favorite detail error: {e}", "error")
            return {"total": 0, "list": [], "page": page, "page_size": page_size}
    
    async def get_user_series_list(self, user_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取用户的合集列表（不需要登录）"""
        self._log(f"Getting user series list: user_id={user_id}")
        
        # 新的API不需要WBI签名，参数也不同
        params = {
            "mid": user_id,
            "page_num": page,
            "page_size": min(page_size, 50),
            "web_location": "333.1387",
        }
        
        url = f"{BASE_URL}{USER_SERIES}?{urlencode(params)}"
        self._log(f"[DEBUG] Series API URL: {url[:200]}")
        
        try:
            response = await self.request("GET", url)
            self._log(f"[DEBUG] Series API response code: {response.get('code', 'N/A')}, keys: {list(response.keys()) if isinstance(response, dict) else type(response)}")
            import json
            self._log(f"[DEBUG] Series API full response: {json.dumps(response, ensure_ascii=False)[:800]}")
            
            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                items_lists = data.get("items_lists", {})
                self._log(f"[DEBUG] Series data keys: {list(data.keys())}, items_lists keys: {list(items_lists.keys())}")
                
                # 获取合集列表（先找seasons_list，如果没有就找series_list）
                series_list = items_lists.get("seasons_list", []) or items_lists.get("series_list", []) or []
                self._log(f"[DEBUG] Series list count: {len(series_list)}")
                if len(series_list) > 0:
                    self._log(f"[DEBUG] First series item keys: {list(series_list[0].keys())}")
                
                result = []
                for series in series_list:
                    # 从第一个视频获取封面
                    first_archive = (series.get("archives", []) or [])[0] if series.get("archives") else {}
                    cover = first_archive.get("pic", "") or ""
                    
                    result.append({
                        "id": str(series.get("season_id", series.get("series_id", ""))),
                        "title": series.get("name", series.get("title", "")),
                        "cover": self._fix_bili_url(cover),
                        "description": series.get("description", series.get("subtitle", "")),
                        "mid": str(user_id),
                        "count": len(series.get("archives", [])),
                        "ctime": first_archive.get("ctime", 0),
                    })
                
                page_info = items_lists.get("page", {})
                total = page_info.get("total", len(result))
                
                return {
                    "total": total,
                    "list": result,
                    "page": page,
                    "page_size": page_size,
                }
            else:
                return {"total": 0, "list": [], "page": page, "page_size": page_size}
                
        except Exception as e:
            self._log(f"Get user series list error: {e}", "error")
            return {"total": 0, "list": [], "page": page, "page_size": page_size}
    
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
    
    def _fix_bili_url(self, url: str) -> str:
        """修复 B站图片/封面 URL（处理协议相对和缺失协议头的格式）
        
        B站 API 返回的 URL 可能有多种格式：
        - //i0.hdslb.com/... （协议相对，需补 https:）
        - /i0.hdslb.com/... （缺失协议头，需补 https://）
        - https://i0.hdslb.com/... （已是完整 URL，无需处理）
        """
        if not url:
            return url
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/i") and "hdslb.com" in url:
            return "https://" + url[1:]
        return url

    def _parse_video_result(self, item: Dict) -> SearchResult:
        """解析视频搜索结果（去除 HTML 标签，修复封面 URL）"""
        import re
        raw_title = item.get("title", "")
        raw_desc = item.get("description", "")
        # 去除 B站返回的 <em class="keyword"> 等 HTML 标签
        title = re.sub(r'<[^>]+>', '', raw_title)
        desc = re.sub(r'<[^>]+>', '', raw_desc)

        cover = self._fix_bili_url(item.get("pic", ""))

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
            coins=item.get("coin", 0),
            comments=item.get("review", 0),
            shares=item.get("share", 0),
            collects=item.get("fav", 0),
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
            cover=self._fix_bili_url(item.get("upic", "")),
            url=f"https://space.bilibili.com/{item.get('mid', '')}",
            platform="bili",
            type="user",
            followers=item.get("fans", 0),
            videos=item.get("videos", 0),
            raw_data=item,
        )
    
    def _parse_article_result(self, item: Dict) -> SearchResult:
        """解析专栏搜索结果"""
        image_urls = item.get("image_urls", [])
        cover = self._fix_bili_url(image_urls[0]) if image_urls else ""
        title = re.sub(r'<[^>]+>', '', item.get("title", ""))
        article_id = str(item.get("id", ""))
        return SearchResult(
            id=article_id,
            title=title,
            desc=item.get("desc", ""),
            author=item.get("author", ""),
            author_id=str(item.get("mid", "")),
            cover=cover,
            url=f"https://www.bilibili.com/read/cv{article_id}",
            platform="bili",
            type="article",
            views=item.get("view", 0),
            likes=item.get("like", 0),
            comments=item.get("reply", 0),
            create_time=str(item.get("pubdate", 0)),
            raw_data=item,
        )
    
    def _parse_bangumi_result(self, item: Dict) -> SearchResult:
        """解析番剧搜索结果"""
        media_score = item.get("media_score", {})
        rating = item.get("rating", {})
        score = media_score.get("score") or rating.get("score") or 0
        score_count = media_score.get("user_count") or rating.get("count") or 0
        return SearchResult(
            id=str(item.get("season_id", "")),
            title=item.get("title", ""),
            desc=item.get("desc", ""),
            author="",
            author_id="",
            cover=self._fix_bili_url(item.get("cover", "")),
            url=item.get("url", ""),
            platform="bili",
            type="bangumi",
            likes=score,
            comments=score_count,
            views=item.get("view", 0),
            create_time=str(item.get("pubtime", "")),
            raw_data=item,
        )

    def _parse_movie_result(self, item: Dict) -> SearchResult:
        """解析影视搜索结果"""
        media_score = item.get("media_score", {})
        rating = item.get("rating", {})
        score = media_score.get("score") or rating.get("score") or 0
        score_count = media_score.get("user_count") or rating.get("count") or 0
        return SearchResult(
            id=str(item.get("season_id", "")),
            title=item.get("title", ""),
            desc=item.get("desc", ""),
            author="",
            author_id="",
            cover=self._fix_bili_url(item.get("cover", "")),
            url=item.get("url", ""),
            platform="bili",
            type="movie",
            likes=score,
            comments=score_count,
            views=item.get("view", 0),
            create_time=str(item.get("pubtime", "")),
            raw_data=item,
        )
    
    def _parse_live_result(self, item: Dict) -> SearchResult:
        """解析直播搜索结果（live_room）"""
        title = re.sub(r'<[^>]+>', '', item.get("title", ""))
        return SearchResult(
            id=str(item.get("roomid", "")),
            title=title,
            desc=item.get("cate_name", ""),
            author=item.get("uname", ""),
            author_id=str(item.get("uid", "")),
            cover=self._fix_bili_url(item.get("cover", "")),
            url=f"https://live.bilibili.com/{item.get('roomid', '')}",
            platform="bili",
            type="live",
            views=item.get("online", 0),
            raw_data=item,
        )

    def _parse_live_user_result(self, item: Dict) -> SearchResult:
        """解析直播主播搜索结果（live_user）"""
        uid = str(item.get("uid", ""))
        uname = re.sub(r'<[^>]+>', '', item.get("uname", ""))
        return SearchResult(
            id=uid,
            title=uname,
            desc=item.get("cate_name", ""),
            author=uname,
            author_id=uid,
            cover=self._fix_bili_url(item.get("uface", "")),
            url=f"https://space.bilibili.com/{uid}",
            platform="bili",
            type="user",
            followers=item.get("attentions", 0),
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
            video_cover=self._fix_bili_url(data.get("pic", "")),
            duration=data.get("duration", 0),
            likes=data.get("stat", {}).get("like", 0),
            coins=data.get("stat", {}).get("coin", 0),
            comments=data.get("stat", {}).get("reply", 0),
            shares=data.get("stat", {}).get("share", 0),
            collects=data.get("stat", {}).get("favorite", 0),
            views=data.get("stat", {}).get("view", 0),
            tags=[tag.get("tag_name", "") for tag in data.get("tag", [])],
            create_time=str(data.get("pubdate", "")),
            raw_data=data,
        )
    
    def _parse_user_video_result(self, item: Dict, user_id: str) -> SearchResult:
        """解析用户视频列表结果
        
        B站 /x/space/wbi/arc/search 返回的 vlist 字段较精简，
        常见字段：play(播放), comment(评论), video_review(弹幕),
        favorites(收藏), length, created, description 等。
        like/coin/share 通常不存在，保持 0 即可。
        """
        return SearchResult(
            id=item.get("bvid", ""),
            title=item.get("title", ""),
            desc=item.get("description", ""),
            author=item.get("author", ""),
            author_id=user_id,
            cover=self._fix_bili_url(item.get("pic", "")),
            url=f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            platform="bili",
            type="video",
            likes=item.get("like", 0),
            coins=item.get("coin", 0),
            comments=item.get("review") or item.get("comment", 0),
            shares=item.get("share", 0),
            collects=item.get("fav") or item.get("favorites") or item.get("stow", 0),
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
    # 字幕相关
    # =========================================================================
    
    async def get_subtitles(self, bvid: str) -> List[Dict]:
        """获取视频字幕列表（先拿 aid/cid，再调 /x/player/wbi/v2）"""
        self._log(f"Getting subtitles for: {bvid}")

        # 第 1 步：用 bvid 拿 aid + cid
        view_url = f"{BASE_URL}/x/web-interface/view?bvid={bvid}"
        try:
            view_resp = await self.request("GET", view_url)
            if not (isinstance(view_resp, dict) and view_resp.get("code") == 0):
                msg = view_resp.get("message", "view api failed") if isinstance(view_resp, dict) else "view request failed"
                self._log(f"Get subtitles failed (view): {msg}", "warning")
                return []
            aid = view_resp["data"]["aid"]
            pages = view_resp["data"].get("pages", [])
            if pages:
                cid = pages[0]["cid"]
            else:
                cid = view_resp["data"].get("cid", 0)
            self._log(f"Got aid={aid}, cid={cid}")
        except Exception as e:
            self._log(f"Get subtitles error (view step): {e}", "error")
            return []

        # 第 2 步：用 aid + cid 调 /x/player/wbi/v2（需要 WBI 签名）
        # 参照真实浏览器请求，加上 dm_* 反爬参数
        params = {
            "aid": aid,
            "cid": cid,
            "isGaiaAvoided": "false",
            "web_location": "1315873",
            "dm_img_list": "[]",
            "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ==",  # Base64("WebGL 1.0 (OpenGLES 2.0 Chromium)")
            "dm_cover_img_str": "QU5HTEUgKE5WSURJQSk=",
            "dm_img_inter": '{"ds":[],"wh":[1920,1080,24],"of":[0,0,0]}',
        }
        query_string = await self._sign_params(params)
        player_url = f"{BASE_URL}/x/player/wbi/v2?{query_string}"

        try:
            player_resp = await self.request("GET", player_url)

            # Debug: 打印完整响应，确认字幕数据
            import json as _json
            self._log(f"Player response (first 800 chars): {_json.dumps(player_resp, ensure_ascii=False)[:800]}", "debug")

            if isinstance(player_resp, dict) and player_resp.get("code") == 0:
                subtitle_info = player_resp.get("data", {}).get("subtitle", {})
                subtitles = subtitle_info.get("subtitles", [])
                # 调试：打印关键字段
                need_login = player_resp.get("data", {}).get("need_login_subtitle", False)
                self._log(f"Got {len(subtitles)} subtitle(s), need_login_subtitle={need_login}", "debug")
                self._log(f"Player response (first 800 chars): {str(player_resp)[:800]}", "debug")
                return subtitles
            else:
                msg = player_resp.get("message", "Unknown error") if isinstance(player_resp, dict) else "Request failed"
                self._log(f"Get subtitles failed (player): {msg}", "warning")
                return []
        except Exception as e:
            self._log(f"Get subtitles error (player step): {e}", "error")
            return []
    
    async def download_subtitle(self, subtitle_url: str, format: str = "srt") -> str:
        """下载字幕并转换为指定格式"""
        self._log(f"Downloading subtitle: {subtitle_url}")
        
        try:
            # 修复 URL（可能需要补协议头）
            if subtitle_url.startswith("//"):
                subtitle_url = "https:" + subtitle_url
            
            response = await self.request("GET", subtitle_url)
            
            self._log(f"Subtitle response type={type(response).__name__}, preview={str(response)[:200]}", "debug")
            
            # 兼容多种响应格式
            data = None
            if isinstance(response, list):
                data = response
            elif isinstance(response, dict):
                # { "code": 0, "data": [...] }
                if "data" in response and isinstance(response["data"], list):
                    data = response["data"]
                # { "body": [...] }
                elif "body" in response and isinstance(response["body"], list):
                    data = response["body"]
                else:
                    self._log(f"Subtitle dict keys: {list(response.keys())[:10]}", "warning")
            
            if not data:
                self._log(f"Subtitle content empty or unknown format: {type(response).__name__}", "warning")
                return ""
            
            if format == "srt":
                return self._convert_to_srt(data)
            elif format == "ass":
                return self._convert_to_ass(data)
            else:
                import json
                return json.dumps(data, ensure_ascii=False, indent=2)
            
        except Exception as e:
            self._log(f"Download subtitle error: {e}", "error")
            return ""
    
    def _convert_to_srt(self, data: List[Dict]) -> str:
        """B站字幕 JSON → SRT 格式"""
        srt_lines = []
        
        for i, item in enumerate(data, 1):
            start = self._format_time(item.get("from", 0.0))
            end = self._format_time(item.get("to", 0.0))
            content = item.get("content", "")
            
            srt_lines.append(f"{i}\n{start} --> {end}\n{content}\n")
        
        return "\n".join(srt_lines)
    
    def _convert_to_ass(self, data: List[Dict]) -> str:
        """B站字幕 JSON → ASS 格式（简化版）"""
        ass_lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1920",
            "PlayResY: 1080",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Default,SimHei,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,30,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        
        for item in data:
            start = self._format_time_ass(item.get("from", 0.0))
            end = self._format_time_ass(item.get("to", 0.0))
            content = item.get("content", "").replace("\n", "\\N")
            
            ass_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{content}")
        
        return "\n".join(ass_lines)
    
    def _format_time(self, seconds: float) -> str:
        """秒数 → SRT 时间格式 (HH:MM:SS,mmm)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    
    def _format_time_ass(self, seconds: float) -> str:
        """秒数 → ASS 时间格式 (H:MM:SS.cc)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds - int(seconds)) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    
    # =========================================================================
    # 弹幕相关
    # =========================================================================

    async def get_danmaku(self, bvid: str, cid: int = 0) -> List[Dict]:
        """获取视频弹幕列表

        Args:
            bvid: B站视频 BV 号
            cid: 分P ID，多P视频必填

        Returns:
            弹幕列表，每个元素包含 time, type, font_size, color, timestamp, pool, user_id, dmid, text
        """
        self._log(f"Getting danmaku for: {bvid}, cid={cid}")

        try:
            # 先获取视频详情拿到 cid
            view_url = f"{BASE_URL}/x/web-interface/view?bvid={bvid}"
            view_resp = await self.request("GET", view_url)
            if not (isinstance(view_resp, dict) and view_resp.get("code") == 0):
                self._log(f"Get danmaku failed (view): {view_resp}", "warning")
                return []

            pages = view_resp["data"].get("pages", [])
            target_cid = cid or (pages[0]["cid"] if pages else None)
            if not target_cid:
                self._log("Cannot get cid for danmaku", "warning")
                return []

            # 获取弹幕
            import re
            danmaku_url = f"{BASE_URL}/x/v1/dm/list.so?oid={target_cid}"
            danmaku_resp = await self.request("GET", danmaku_url)

            # 处理不同类型的响应
            xml_text = None
            if isinstance(danmaku_resp, str):
                xml_text = danmaku_resp
            elif isinstance(danmaku_resp, dict):
                # _request_api 在 JSON 解析失败时返回 {'text': content, 'status': ...}
                if 'text' in danmaku_resp:
                    xml_text = danmaku_resp['text']
                else:
                    self._log(f"Danmaku response is dict: {danmaku_resp}", "warning")
                    return []
            else:
                self._log(f"Danmaku unexpected type: {type(danmaku_resp)}", "warning")
                return []

            if not xml_text:
                self._log("Danmaku xml_text is empty", "warning")
                return []

            # 解析 XML 弹幕
            pattern = r'<d p="([^"]+)">([^<]+)</d>'
            matches = re.findall(pattern, xml_text)
            danmaku_list = []
            for p, text in matches:
                parts = p.split(",")
                if len(parts) >= 8:
                    danmaku_list.append({
                        "time": float(parts[0]),
                        "type": int(parts[1]),
                        "font_size": int(parts[2]),
                        "color": parts[3],
                        "timestamp": parts[4],
                        "pool": int(parts[5]),
                        "user_id": parts[6],
                        "dmid": parts[7],
                        "text": text,
                    })

            self._log(f"Got {len(danmaku_list)} danmaku for {bvid}")
            return danmaku_list

        except Exception as e:
            self._log(f"Get danmaku error: {e}", "error")
            return []

    async def download_danmaku(self, bvid: str, format: str = "json") -> str:
        """下载弹幕文件

        Args:
            bvid: B站视频 BV 号
            format: 格式 'json' 或 'ass'

        Returns:
            弹幕文件内容
        """
        self._log(f"Downloading danmaku for: {bvid}, format={format}")

        try:
            danmaku_list = await self.get_danmaku(bvid)
            if not danmaku_list:
                return ""

            if format == "json":
                import json
                return json.dumps(danmaku_list, ensure_ascii=False, indent=2)
            elif format == "ass":
                import re
                lines = ["[Script Info]", "Title: Danmaku ASS", "ScriptType: v4.00+", "",
                         "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                         "Style: Default,Sans,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1",
                         "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
                for d in danmaku_list:
                    t = d.get("time", 0)
                    h = int(t // 3600)
                    m = int((t % 3600) // 60)
                    s = t % 60
                    lines.append(f'Dialogue: 0,{h}:{m:02d}:{s:06.3f},{h}:{m:02d}:{s+5:06.3f},Default,,0,0,0,,{d.get("text", "")}')
                return "\n".join(lines)
            else:
                return ""

        except Exception as e:
            self._log(f"Download danmaku error: {e}", "error")
            return ""

    # =========================================================================
    # 视频信息
    # =========================================================================

    async def get_video_info(self, bvid: str) -> Dict:
        """获取视频详细信息

        Args:
            bvid: B站视频 BV 号

        Returns:
            视频详细信息（aid, cid, title, description, owner, stat, pages 等）
        """
        self._log(f"Getting video info for: {bvid}")

        try:
            view_url = f"{BASE_URL}/x/web-interface/view?bvid={bvid}"
            view_resp = await self.request("GET", view_url)

            if isinstance(view_resp, dict) and view_resp.get("code") == 0:
                data = view_resp.get("data", {})
                self._log(f"Got video info: {data.get('title', 'unknown')}")
                return data
            else:
                self._log(f"Failed to get video info: {view_resp}", "warning")
                return {}
        except Exception as e:
            self._log(f"Get video info error: {e}", "error")
            return {}

    # =========================================================================
    # 作品数据统计
    # =========================================================================

    async def get_stats(self, bvid: str = "", aid: int = 0) -> Dict:
        """获取视频作品数据（播放量/点赞/投币/收藏/评论/分享/弹幕数）

        Args:
            bvid: BV 号
            aid: AV 号

        Returns:
            包含 stat 信息的字典
        """
        self._log(f"Getting stats for: bvid={bvid}, aid={aid}")

        if not bvid and not aid:
            self._log("Must provide bvid or aid", "error")
            return {}

        params = {}
        if bvid:
            params["bvid"] = bvid
        if aid:
            params["aid"] = aid

        try:
            url = f"{BASE_URL}/x/web-interface/view?{urlencode(params)}"
            response = await self.request("GET", url)

            if isinstance(response, dict) and response.get("code") == 0:
                info = response.get("data", {})
                stat = info.get("stat", {})
                owner = info.get("owner", {})

                return {
                    "bvid": info.get("bvid", ""),
                    "aid": info.get("aid", ""),
                    "title": info.get("title", ""),
                    "description": info.get("desc", "")[:200],
                    "owner_name": owner.get("name", ""),
                    "owner_mid": owner.get("mid", ""),
                    "duration_seconds": info.get("duration", 0),
                    "pubdate": info.get("pubdate", 0),
                    "stat": {
                        "view": stat.get("view", 0),
                        "like": stat.get("like", 0),
                        "coin": stat.get("coin", 0),
                        "favorite": stat.get("favorite", 0),
                        "reply": stat.get("reply", 0),
                        "share": stat.get("share", 0),
                        "danmaku": stat.get("danmaku", 0),
                    },
                }
            else:
                msg = response.get("message", "Unknown error") if isinstance(response, dict) else "Request failed"
                self._log(f"Get stats failed: {msg}", "warning")
                return {}

        except Exception as e:
            self._log(f"Get stats error: {e}", "error")
            return {}

    # =========================================================================
    # 评论管理
    # =========================================================================

    async def get_comments_paged(
        self,
        bvid: str,
        page: int = 1,
        page_size: int = 20,
        sort: int = 0,
        offset: str = "",
    ) -> Dict:
        """获取评论列表（游标分页版）

        Args:
            bvid: BV 号
            page: 页码（1 开始，保留兼容性）
            page_size: 每页条数
            sort: 排序 0=最热 1=最新 2=最早
            offset: 游标偏移值（用于加载更多，从响应的 next_offset 中获取）

        Returns:
            {"total": int, "page": int, "page_size": int, "comments": [...], 
             "cursor": {...}, "next_offset": str, "has_more": bool}
        """
        self._log(f"Getting comments for: {bvid}, page={page}, sort={sort}, offset={offset[:50] if offset else 'empty'}")

        try:
            # 先获取视频信息，拿到 aid（avid）
            view_url = f"{BASE_URL}/x/web-interface/view?bvid={bvid}"
            view_resp = await self.request("GET", view_url)
            if not (isinstance(view_resp, dict) and view_resp.get("code") == 0):
                self._log(f"Get comments failed (view): {view_resp}", "warning")
                return {"total": 0, "page": page, "page_size": page_size, "comments": [], "cursor": {}, "next_offset": "", "has_more": False}

            # 评论API的 oid 参数需要使用 aid（avid），不是 cid！
            # 参考: https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/reply/reply_list.md
            target_aid = view_resp["data"].get("aid")
            if not target_aid:
                self._log(f"Get comments failed: no aid in view response", "warning")
                return {"total": 0, "page": page, "page_size": page_size, "comments": [], "cursor": {}, "next_offset": "", "has_more": False}
            self._log(f"[DEBUG] Using aid={target_aid} for comment API")

            # 将 sort 参数映射到正确的 mode 值：0=最热(mode=3), 1=最新(mode=2), 2=最早(mode=1)
            mode_map = {0: 3, 1: 2, 2: 1}
            target_mode = mode_map.get(sort, 3)
            
            # 最早(mode=1)时，WBI API 的 pagination_str 排序不可靠，改用非 WBI 旧版 API
            # 非 WBI API 使用 pn 页码分页，避免 next_offset 在时间排序下乱序的问题
            if target_mode == 1:
                # 非 WBI 旧版评论 API（mode=1 时使用）
                # pagination_str 固定为空，依赖 pn 页码分页
                non_wbi_params = {
                    "type": 1,
                    "oid": target_aid,
                    "mode": target_mode,
                    "pn": page,
                    "ps": page_size,
                }
                import urllib.parse
                qs = urllib.parse.urlencode(non_wbi_params)
                url = f"{BASE_URL}/x/v2/reply/main?{qs}"
                self._log(f"[DEBUG] Comment API (non-WBI) URL: {url[:200]}...")
                resp = await self.request("GET", url)
            else:
                # WBI 签名 API（最热/最新模式）
                pagination_str = '{"offset":""}'
                if offset:
                    pagination_str = f'{{"offset":"{offset}"}}'
                params = {
                    "type": 1,
                    "oid": target_aid,
                    "mode": target_mode,
                    "pagination_str": pagination_str,
                    "ps": page_size,
                }
                query_string = await self._sign_params(params)
                url = f"{BASE_URL}/x/v2/reply/wbi/main?{query_string}"
                self._log(f"[DEBUG] Comment API (WBI) URL: {url[:200]}...")
                resp = await self.request("GET", url)
            resp = await self.request("GET", url)

            # 调试日志：打印原始响应
            resp_code = resp.get('code') if isinstance(resp, dict) else 'N/A'
            self._log(f"[DEBUG] Comment API raw resp code={resp_code}")
            
            # 如果 code 不是 0，打印详细错误
            if isinstance(resp, dict) and resp_code != 0:
                self._log(f"[DEBUG] Comment API error: {resp}", "warning")
                import json
                self._log(f"[DEBUG] Full resp JSON: {json.dumps(resp, ensure_ascii=False)[:500]}", "warning")
                return {"total": 0, "page": page, "page_size": page_size, "comments": [], "cursor": {}, "next_offset": "", "has_more": False}

            if isinstance(resp, dict) and resp.get("code") == 0:
                replies = resp.get("data", {})
                # 调试日志：打印 replies 结构
                self._log(f"[DEBUG] Comment replies keys: {list(replies.keys()) if isinstance(replies, dict) else type(replies)}")

                # B站 WBI 评论 API 的 total 在 cursor.all_count 中
                cursor = replies.get("cursor", {})
                import json
                self._log(f"[DEBUG] Full cursor: {json.dumps(cursor, ensure_ascii=False)[:500]}")
                comment_total = cursor.get("all_count") or cursor.get("all_total") or replies.get("all_total") or replies.get("total") or len(replies.get("replies") or [])
                self._log(f"[DEBUG] Comment cursor: all_count={cursor.get('all_count', 'N/A')}, is_end={cursor.get('is_end', 'N/A')}, next_offset={cursor.get('pagination_reply', {}).get('next_offset', 'N/A') or cursor.get('next_offset', 'N/A')}, Final comment_total: {comment_total}")
                self._log(f"[DEBUG] Comment replies count: {len(replies.get('replies') or [])}")
                comments = []
                for r in replies.get("replies", []) or []:
                    member = r.get("member", {})
                    c = r.get("content", {})
                    comments.append({
                        "rpid": r.get("rpid"),
                        "user_name": member.get("uname", ""),
                        "user_avatar": member.get("avatar", ""),
                        "mid": member.get("mid"),
                        "message": c.get("message", ""),
                        "like_count": r.get("like_count", 0),
                        "ctime": r.get("ctime"),
                        "replies_count": r.get("rcount", 0),
                    })
                self._log(f"[DEBUG] Parsed {len(comments)} comments")
                
                # 提取下一页的 offset
                # WBI API: next_offset 在 pagination_reply 中; 非 WBI (mode=1): 用页码分页，编码为 __page:N
                if target_mode == 1:
                    # 非 WBI API，用 pn 分页，不返回 next_offset（前端改用 page+1）
                    next_offset = ""
                else:
                    next_offset = (
                        cursor.get("pagination_reply", {}).get("next_offset", "")
                        or cursor.get("next_offset", "")
                    )
                has_more = not bool(cursor.get("is_end", True))
                
                return {
                    "total": comment_total,
                    "page": page,
                    "page_size": page_size,
                    "comments": comments,
                    "cursor": cursor,
                    "next_offset": next_offset,
                    "has_more": has_more,
                }
            else:
                # 打印错误信息
                err_msg = resp.get("message", "") if isinstance(resp, dict) else ""
                self._log(f"[DEBUG] Comment API failed: code={resp.get('code') if isinstance(resp, dict) else 'N/A'}, msg={err_msg}", "warning")
                return {"total": 0, "page": page, "page_size": page_size, "comments": [], "cursor": {}, "next_offset": "", "has_more": False}

        except Exception as e:
            self._log(f"Get comments error: {e}", "error")
            return {"total": 0, "page": page, "page_size": page_size, "comments": [], "cursor": {}, "next_offset": "", "has_more": False}

    async def send_comment(
        self,
        bvid: str,
        message: str,
        parent: int = 0,
        root: int = 0,
        csrf: str = "",
    ) -> Dict:
        """发送评论（需要登录态）

        Args:
            bvid: BV 号
            message: 评论内容
            parent: 回复的评论ID（0=一级评论）
            root: 根评论ID
            csrf: CSRF token（从 cookie 中的 bili_jct 提取）

        Returns:
            {"success": bool, "rpid": int, "message": str}
        """
        self._log(f"Sending comment for: {bvid}, message={message[:50]}...")

        if not csrf and self.config.cookie:
            # 尝试从 cookie 中提取 bili_jct
            import re
            match = re.search(r'bili_jct=([^;]+)', self.config.cookie)
            if match:
                csrf = match.group(1)
                self._log(f"[DEBUG] Auto-extracted csrf from cookie")

        if not csrf:
            self._log("CSRF token required for sending comment", "error")
            return {"success": False, "message": "缺少 CSRF token"}

        try:
            # 拿 aid（评论 API 需要的是 aid，不是 cid）
            view_url = f"{BASE_URL}/x/web-interface/view?bvid={bvid}"
            view_resp = await self.request("GET", view_url)
            if not (isinstance(view_resp, dict) and view_resp.get("code") == 0):
                self._log(f"Send comment failed (view): {view_resp}", "warning")
                return {"success": False, "message": "视频不存在"}

            target_aid = view_resp["data"].get("aid")
            if not target_aid:
                self._log(f"Send comment failed: no aid in view response", "warning")
                return {"success": False, "message": "无法获取视频信息"}

            self._log(f"[DEBUG] Using aid={target_aid} for send comment API")

            payload = {
                "type": 1,
                "oid": target_aid,
                "message": message,
                "csrf_token": csrf,
                "csrf": csrf,
            }
            if parent > 0:
                payload["parent"] = parent
            if root > 0:
                payload["root"] = root

            url = f"{BASE_URL}/x/v2/reply/add"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
            }

            resp = await self.request("POST", url, data=payload, headers=headers)

            if isinstance(resp, dict) and resp.get("code") == 0:
                return {
                    "success": True,
                    "rpid": resp.get("data", {}).get("rpid", -1),
                    "message": "评论成功",
                }
            else:
                msg = resp.get("message", "评论失败") if isinstance(resp, dict) else "评论失败"
                return {"success": False, "message": msg}

        except Exception as e:
            self._log(f"Send comment error: {e}", "error")
            return {"success": False, "message": str(e)}

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

    # =========================================================================
    # 历史观看记录（需要登录）
    # =========================================================================

    async def get_watch_history(
        self,
        max_results: int = 20,
        max_oid: int = 0,
        view_at: int = 0,
        business: str = "",
        history_type: str = "all",
    ) -> Dict[str, Any]:
        """获取当前登录用户的历史观看记录

        使用 B站 /x/web-interface/history/cursor 接口，需要登录态 Cookie
        该接口使用游标分页，通过 max（oid）和 view_at 定位下一页

        Args:
            max_results: 每页返回数量（默认20）
            max_oid: 上一页最后一条记录的 oid（游标分页用，首次请求传0）
            view_at: 上一页最后一条记录的 view_at 时间戳（游标分页用，首次请求传0）
            business: 业务类型过滤（空字符串=全部, archive=视频, live=直播, article=专栏）
            history_type: 类型过滤（all=全部）

        Returns:
            {"list": List[Dict], "cursor": {...}, "has_more": bool}
            cursor 包含下一页所需的 max 和 view_at 值
        """
        self._log(f"Getting watch history: ps={max_results}, max={max_oid}, view_at={view_at}")

        if not self.config.cookie:
            self._log("No cookie, cannot get watch history", "warning")
            return {"list": [], "cursor": {}, "has_more": False}

        try:
            params: Dict[str, Any] = {
                "max": max_oid,
                "view_at": view_at,
                "business": business,
                "ps": min(max_results, 50),
                "type": history_type,
                "web_location": "333.1391",
            }

            query_string = await self._sign_params(params)
            url = f"{BASE_URL}{HISTORY_CURSOR}?{query_string}"

            response = await self.request("GET", url)

            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                items = data.get("list", []) or []
                cursor = data.get("cursor", {})

                self._log(f"Got {len(items)} history items, cursor={cursor}")

                result = []
                for item in items:
                    history = item.get("history", {})
                    bvid = history.get("bvid", "")
                    stat = item.get("stat", {}) or {}

                    result.append({
                        "bvid": bvid,
                        "title": item.get("title", ""),
                        "cover": self._fix_bili_url(
                            item.get("cover", "")
                            or (item.get("covers") or [None])[0]
                            or ""
                        ),
                        "author": item.get("author_name", ""),
                        "author_face": self._fix_bili_url(item.get("author_face", "")),
                        "author_id": str(item.get("author_mid", "")),
                        "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                        "duration": item.get("duration", 0),
                        "view_at": item.get("view_at", 0),
                        "progress": item.get("progress", 0),
                        "show_title": item.get("show_title", ""),
                        "badge": item.get("badge", ""),
                        "tag_name": item.get("tag_name", ""),
                        "is_fav": item.get("is_fav", 0),
                        "videos": item.get("videos", 1),
                        "new_desc": item.get("new_desc", ""),
                        "is_finish": item.get("is_finish", 0),
                        "stat": {
                            "view": stat.get("view", 0),
                            "like": stat.get("like", 0),
                            "coin": stat.get("coin", 0),
                            "favorite": stat.get("favorite", 0),
                            "reply": stat.get("reply", 0),
                        },
                        "history": {
                            "oid": history.get("oid", 0),
                            "bvid": bvid,
                            "page": history.get("page", 1),
                            "cid": history.get("cid", 0),
                            "part": history.get("part", ""),
                            "business": history.get("business", ""),
                        },
                        "raw_data": item,
                    })

                has_more = cursor.get("ps", 0) > 0 and len(items) > 0

                return {
                    "list": result,
                    "cursor": {
                        "max": cursor.get("max", 0),
                        "view_at": cursor.get("view_at", 0),
                        "business": cursor.get("business", ""),
                        "ps": cursor.get("ps", 0),
                    },
                    "has_more": has_more,
                }
            else:
                code = response.get("code", -1) if isinstance(response, dict) else -1
                msg = response.get("message", "") if isinstance(response, dict) else str(response)[:200]
                self._log(f"Get watch history failed: code={code}, msg={msg}", "warning")
                return {"list": [], "cursor": {}, "has_more": False}

        except Exception as e:
            self._log(f"Get watch history error: {e}", "error")
            return {"list": [], "cursor": {}, "has_more": False}

    async def search_watch_history(
        self,
        business: str = "archive",
        page: int = 1,
        page_size: int = 20,
        keyword: str = "",
        add_time_start: int = 0,
        add_time_end: int = 0,
    ) -> Dict[str, Any]:
        """搜索历史观看记录（支持时间筛选和关键词搜索）

        使用 B站 /x/web-interface/history/search 接口
        支持按类型（视频/直播/专栏）、时间范围、关键词筛选

        Args:
            business: 业务类型（archive=视频, live=直播, article=专栏）
            page: 页码（从1开始）
            page_size: 每页数量
            keyword: 搜索关键词
            add_time_start: 起始时间戳（秒），0=不限
            add_time_end: 结束时间戳（秒），0=不限

        Returns:
            {"list": List[Dict], "total": int, "page": int, "has_more": bool}
        """
        self._log(f"Searching watch history: business={business}, page={page}, keyword={keyword}, start={add_time_start}, end={add_time_end}")

        if not self.config.cookie:
            self._log("No cookie, cannot search watch history", "warning")
            return {"list": [], "total": 0, "page": page, "has_more": False}

        try:
            params: Dict[str, Any] = {
                "pn": page,
                "keyword": keyword,
                "business": business,
                "add_time_start": add_time_start,
                "add_time_end": add_time_end,
                "arc_max_duration": 0,
                "arc_min_duration": 0,
                "device_type": 0,
                "web_location": "333.1391",
            }

            query_string = await self._sign_params(params)
            url = f"{BASE_URL}{HISTORY_SEARCH}?{query_string}"

            response = await self.request("GET", url)

            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                items = data.get("list", []) or []
                page_info = data.get("page", {}) or {}

                self._log(f"Got {len(items)} history search items")

                result = []
                for item in items:
                    history = item.get("history", {})
                    bvid = history.get("bvid", "")
                    stat = item.get("stat", {}) or {}

                    result.append({
                        "bvid": bvid,
                        "title": item.get("title", ""),
                        "cover": self._fix_bili_url(
                            item.get("cover", "")
                            or (item.get("covers") or [None])[0]
                            or ""
                        ),
                        "author": item.get("author_name", ""),
                        "author_face": self._fix_bili_url(item.get("author_face", "")),
                        "author_id": str(item.get("author_mid", "")),
                        "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                        "duration": item.get("duration", 0),
                        "view_at": item.get("view_at", 0),
                        "progress": item.get("progress", 0),
                        "show_title": item.get("show_title", ""),
                        "badge": item.get("badge", ""),
                        "tag_name": item.get("tag_name", ""),
                        "is_fav": item.get("is_fav", 0),
                        "videos": item.get("videos", 1),
                        "new_desc": item.get("new_desc", ""),
                        "is_finish": item.get("is_finish", 0),
                        "stat": {
                            "view": stat.get("view", 0),
                            "like": stat.get("like", 0),
                            "coin": stat.get("coin", 0),
                            "favorite": stat.get("favorite", 0),
                            "reply": stat.get("reply", 0),
                        },
                        "history": {
                            "oid": history.get("oid", 0),
                            "bvid": bvid,
                            "page": history.get("page", 1),
                            "cid": history.get("cid", 0),
                            "part": history.get("part", ""),
                            "business": history.get("business", ""),
                        },
                        "raw_data": item,
                    })

                total = page_info.get("total", 0) or len(result)
                has_more = page * page_size < total

                return {
                    "list": result,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "has_more": has_more,
                }
            else:
                code = response.get("code", -1) if isinstance(response, dict) else -1
                msg = response.get("message", "") if isinstance(response, dict) else str(response)[:200]
                self._log(f"Search watch history failed: code={code}, msg={msg}", "warning")
                return {"list": [], "total": 0, "page": page, "has_more": False}

        except Exception as e:
            self._log(f"Search watch history error: {e}", "error")
            return {"list": [], "total": 0, "page": page, "has_more": False}

    # =========================================================================
    # 关注列表（需要登录）
    # =========================================================================

    async def get_followings(
        self,
        vmid: int = 0,
        page: int = 1,
        page_size: int = 20,
        order_type: str = "desc",
    ) -> Dict[str, Any]:
        """获取当前登录用户的关注列表

        使用 B站 /x/relation/followings 接口，需要登录态 Cookie
        返回关注的 UP 主列表，包含用户基本信息

        Args:
            vmid: 用户UID（0=当前登录用户自己）
            page: 页码（从1开始）
            page_size: 每页数量（最大50）
            order_type: 排序方式（desc=最近关注在前, asc=最早关注在前）

        Returns:
            {"list": List[Dict], "total": int, "page": int, "has_more": bool}
        """
        self._log(f"Getting followings: vmid={vmid}, page={page}, page_size={page_size}")

        if not self.config.cookie:
            self._log("No cookie, cannot get followings", "warning")
            return {"list": [], "total": 0, "page": page, "has_more": False}

        # 当 vmid=0 时，从 Cookie 中提取 DedeUserID
        if vmid == 0:
            vmid = self._extract_user_id_from_cookie()
            if vmid == 0:
                self._log("Cannot extract user ID from cookie", "warning")
                return {"list": [], "total": 0, "page": page, "has_more": False}

        try:
            params: Dict[str, Any] = {
                "vmid": vmid,
                "pn": page,
                "ps": min(page_size, 50),
                "order_type": order_type,
                "order": order_type,
                "web_location": "333.1387",  # 修正：使用正确的 web_location 值
                "gaia_source": "main_web",     # 添加：必要的来源标识
            }

            query_string = await self._sign_params(params)
            url = f"{BASE_URL}{FOLLOWINGS}?{query_string}"

            response = await self.request("GET", url)

            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                items = data.get("list", []) or []
                total = data.get("total", 0) or len(items)

                self._log(f"Got {len(items)} followings, total={total}")

                result = []
                for item in items:
                    result.append({
                        "mid": str(item.get("mid", "")),
                        "uname": item.get("uname", ""),
                        "face": self._fix_bili_url(item.get("face", "")),
                        "sign": item.get("sign", ""),
                        "official_verify": item.get("official_verify", {}),
                        "vip": item.get("vip", {}),
                        "live_status": item.get("live_status", 0),
                        "live_url": item.get("live_url", ""),
                        "mtime": item.get("mtime", 0),
                        "attribute": item.get("attribute", 0),
                        "special": item.get("special", 0),
                        "contract_desc": item.get("contract_desc", ""),
                        "raw_data": item,
                    })

                has_more = page * page_size < total

                return {
                    "list": result,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "has_more": has_more,
                }
            else:
                code = response.get("code", -1) if isinstance(response, dict) else -1
                msg = response.get("message", "") if isinstance(response, dict) else str(response)[:200]
                self._log(f"Get followings failed: code={code}, msg={msg}", "warning")
                return {"list": [], "total": 0, "page": page, "has_more": False}

        except Exception as e:
            self._log(f"Get followings error: {e}", "error")
            return {"list": [], "total": 0, "page": page, "has_more": False}

    # =========================================================================
    # 付费课程（芝士课堂）
    # =========================================================================

    async def get_paid_courses(
        self,
        page: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        """获取当前登录用户的付费课程列表（芝士课堂）

        使用 B站 /pugv/pay/web/my/paid 接口，需要登录态 Cookie

        Args:
            page: 页码（从1开始）
            page_size: 每页数量（最大100）

        Returns:
            {"list": List[Dict], "total": int, "page": int, "has_more": bool}
        """
        self._log(f"Getting paid courses: page={page}, page_size={page_size}")

        if not self.config.cookie:
            self._log("No cookie, cannot get paid courses", "warning")
            return {"list": [], "total": 0, "page": page, "has_more": False}

        try:
            params: Dict[str, Any] = {
                "pn": page,
                "ps": min(page_size, 100),
            }

            url = f"{BASE_URL}{PAID_COURSES}?{urlencode(params)}"

            response = await self.request("GET", url)

            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                items = data.get("data", []) or []
                total = data.get("total", 0) or len(items)
                has_more = data.get("next", False)

                self._log(f"Got {len(items)} paid courses, total={total}")

                result = []
                for item in items:
                    progress = item.get("progress", {})
                    result.append({
                        "id": item.get("id", 0),
                        "pay_gid": item.get("pay_gid", 0),
                        "title": item.get("title", ""),
                        "sub_title": item.get("sub_title", ""),
                        "cover": self._fix_bili_url(item.get("cover", "")),
                        "url": item.get("url", ""),
                        "up_id": str(item.get("up_id", "")),
                        "ep_count": item.get("ep_count", 0),
                        "price": item.get("price", 0),
                        "platformPrice": item.get("platformPrice", 0),
                        "status": item.get("status", 0),
                        "is_expired": item.get("is_expired", False),
                        "expiry_day": item.get("expiry_day", 0),
                        "pay_status": item.get("pay_status", 0),
                        "update_info": item.get("update_info", ""),
                        "seasonStyle": item.get("seasonStyle", 0),
                        "progress": {
                            "last_ep_id": progress.get("last_ep_id", 0),
                            "last_ep_index": progress.get("last_ep_index", ""),
                            "last_time": progress.get("last_time", 0),
                        },
                        "raw_data": item,
                    })

                return {
                    "list": result,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "has_more": has_more,
                }
            else:
                code = response.get("code", -1) if isinstance(response, dict) else -1
                msg = response.get("message", "") if isinstance(response, dict) else str(response)[:200]
                self._log(f"Get paid courses failed: code={code}, msg={msg}", "warning")
                return {"list": [], "total": 0, "page": page, "has_more": False}

        except Exception as e:
            self._log(f"Get paid courses error: {e}", "error")
            return {"list": [], "total": 0, "page": page, "has_more": False}

    async def get_paid_course_detail(
        self,
        season_id: int,
    ) -> Dict[str, Any]:
        """获取付费课程详情和章节列表

        Args:
            season_id: 课程ID（season_id）

        Returns:
            {"title": str, "cover": str, "episodes": List[Dict]}
        """
        self._log(f"Getting paid course detail: season_id={season_id}")

        if not self.config.cookie:
            self._log("No cookie, cannot get paid course detail", "warning")
            return {}

        try:
            params: Dict[str, Any] = {
                "season_id": season_id,
                "platform": "web",
            }

            url = f"{BASE_URL}{PAID_COURSE_DETAIL}?{urlencode(params)}"

            response = await self.request("GET", url)

            # 调试：打印响应状态和数据结构
            if isinstance(response, dict):
                code = response.get("code")
                self._log(f"Course detail response code: {code}, keys: {list(response.keys())}", "debug")
                if code != 0:
                    self._log(f"Response message: {response.get('message')}", "warning")
                
                data = response.get("data", {})
                if data:
                    self._log(f"Data keys: {list(data.keys())}", "debug")
                    self._log(f"Has sections: {'sections' in data}, Has episodes: {'episodes' in data}, Has ep: {'ep' in data}", "debug")

            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                
                # 尝试多种可能的数据结构
                episodes = []
                
                # 结构1：sections -> episodes
                sections = data.get("sections", [])
                if sections:
                    self._log(f"Found {len(sections)} sections", "debug")
                    for section in sections:
                        eps = section.get("episodes", [])
                        self._log(f"Section '{section.get('title', '')}' has {len(eps)} episodes", "debug")
                        for episode in eps:
                            episodes.append({
                                "ep_id": episode.get("id", 0),
                                "aid": episode.get("aid", 0),
                                "cid": episode.get("cid", 0),
                                "title": episode.get("title", ""),
                                "section_title": section.get("title", ""),
                                "duration": episode.get("duration", 0),
                                "page": episode.get("page", 0),
                                "raw_data": episode,
                            })
                
                # 结构2：episodes 直接在根级别
                if not episodes:
                    raw_episodes = data.get("episodes", [])
                    self._log(f"Found {len(raw_episodes)} episodes in root", "debug")
                    for episode in raw_episodes:
                        episodes.append({
                            "ep_id": episode.get("id", 0) or episode.get("ep_id", 0),
                            "aid": episode.get("aid", 0),
                            "cid": episode.get("cid", 0),
                            "title": episode.get("title", ""),
                            "section_title": episode.get("section_title", "") or episode.get("subtitle", ""),
                            "duration": episode.get("duration", 0),
                            "page": episode.get("page", 0),
                            "raw_data": episode,
                        })
                
                # 结构3：ep 字段
                if not episodes:
                    raw_eps = data.get("ep", [])
                    self._log(f"Found {len(raw_eps)} eps in root", "debug")
                    for episode in raw_eps:
                        episodes.append({
                            "ep_id": episode.get("id", 0) or episode.get("ep_id", 0),
                            "aid": episode.get("aid", 0),
                            "cid": episode.get("cid", 0),
                            "title": episode.get("title", "") or episode.get("index_title", ""),
                            "section_title": episode.get("section_title", ""),
                            "duration": episode.get("duration", 0),
                            "page": episode.get("page", 0),
                            "raw_data": episode,
                        })

                self._log(f"Total episodes extracted: {len(episodes)}", "debug")

                return {
                    "title": data.get("title", ""),
                    "cover": self._fix_bili_url(data.get("cover", "")),
                    "desc": data.get("desc", ""),
                    "ep_count": data.get("ep_count", 0) or len(episodes),
                    "update_info": data.get("update_info", ""),
                    "episodes": episodes,
                    "raw_data": data,
                }
            else:
                code = response.get("code", -1) if isinstance(response, dict) else -1
                msg = response.get("message", "") if isinstance(response, dict) else str(response)[:200]
                self._log(f"Get paid course detail failed: code={code}, msg={msg}", "warning")
                return {}

        except Exception as e:
            self._log(f"Get paid course detail error: {e}", "error")
            return {}

    async def get_paid_course_playurl(
        self,
        ep_id: int,
        qn: int = 80,
    ) -> Dict[str, Any]:
        """获取付费课程视频播放地址

        Args:
            ep_id: 章节ID
            qn: 画质质量（80=高清1080P, 64=高清720P, 32=清晰480P, 16=流畅360P）

        Returns:
            {"video_url": str, "audio_url": str, "quality": int, "duration": int}
        """
        self._log(f"Getting paid course playurl: ep_id={ep_id}, qn={qn}")

        if not self.config.cookie:
            self._log("No cookie, cannot get paid course playurl", "warning")
            return {}

        try:
            params: Dict[str, Any] = {
                "ep_id": ep_id,
                "qn": qn,
                "platform": "web",
                "fnval": 4048,
                "fnver": 0,
                "fourk": 1,
            }

            url = f"{BASE_URL}{PAID_COURSE_PLAYURL}?{urlencode(params)}"

            response = await self.request("GET", url)

            if isinstance(response, dict) and response.get("code") == 0:
                data = response.get("data", {})
                
                # 提取视频流
                video_url = ""
                audio_url = ""
                duration = data.get("duration", 0)
                
                # 优先使用 dash 格式（音视频分离）
                dash = data.get("dash", {})
                if dash:
                    video_streams = dash.get("video", [])
                    audio_streams = dash.get("audio", [])
                    
                    if video_streams:
                        # 找到匹配 qn 的视频流
                        matched_stream = None
                        for stream in video_streams:
                            if stream.get("id") == qn:
                                matched_stream = stream
                                break
                        if not matched_stream:
                            matched_stream = video_streams[0]
                        video_url = matched_stream.get("base_url", "")
                    
                    if audio_streams:
                        audio_url = audio_streams[0].get("base_url", "")
                else:
                    # 使用 durl 格式（音视频合一）
                    durl = data.get("durl", [])
                    if durl:
                        video_url = durl[0].get("url", "")

                return {
                    "video_url": video_url,
                    "audio_url": audio_url,
                    "quality": qn,
                    "duration": duration,
                    "quality_list": data.get("quality_description", []),
                    "raw_data": data,
                }
            else:
                code = response.get("code", -1) if isinstance(response, dict) else -1
                msg = response.get("message", "") if isinstance(response, dict) else str(response)[:200]
                self._log(f"Get paid course playurl failed: code={code}, msg={msg}", "warning")
                return {}

        except Exception as e:
            self._log(f"Get paid course playurl error: {e}", "error")
            return {}
