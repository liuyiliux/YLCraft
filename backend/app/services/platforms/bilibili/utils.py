"""
YLCraft — B站工具函数

包含B站相关的辅助功能，如Cookie解析、账号信息提取、
清晰度/分辨率映射、文件大小估算等
"""

import logging
import httpx

from app.services.cookies.manager import CookieManager

logger = logging.getLogger("ylcraft.platforms.bilibili.utils")


# =============================================================================
# B站清晰度映射（共享常量）
# =============================================================================

BILI_QUALITY_MAP = {
    127: "8K",
    126: "杜比视界",
    125: "HDR",
    120: "4K",
    116: "1080P60",
    112: "1080P+",
    80: "1080P",
    64: "720P",
    32: "480P",
    16: "360P",
    6: "240P",
}

# 清晰度编号 → 分辨率（已知固定值，不依赖 API 返回的 width/height）
BILI_RESOLUTION_MAP = {
    127: "7680x4320",   # 8K
    126: "3840x2160",   # 杜比视界
    125: "3840x2160",   # HDR
    120: "3840x2160",   # 4K
    116: "1920x1080",   # 1080P60
    112: "1920x1080",   # 1080P+
    80: "1920x1080",    # 1080P
    64: "1280x720",     # 720P
    32: "854x480",      # 480P（16:9）
    16: "640x360",      # 360P（16:9）
    6: "426x240",       # 240P（16:9）
}

# 各清晰度典型码率 (bps)，用于无 durl size 时估算文件大小
_QUALITY_BITRATE_MAP = {
    127: 80_000_000,
    126: 60_000_000,
    125: 50_000_000,
    120: 35_000_000,
    116: 20_000_000,
    112: 12_000_000,
    80: 6_000_000,
    64: 3_000_000,
    32: 1_500_000,
    16: 800_000,
    6: 400_000,
}


# =============================================================================
# 共享工具函数
# =============================================================================

def _normalize_resolution(res: str) -> str:
    """将分辨率统一为 widthxheight 格式"""
    if not res:
        return ""
    res = res.strip()
    if "x" in res:
        return res
    if res.endswith("p"):
        try:
            h = int(res[:-1])
            w = int(h * 16 / 9)
            return f"{w}x{h}"
        except ValueError:
            return ""
    return res


def _quality_to_resolution(qn: int, fallback_height: int = 0) -> str:
    """根据清晰度编号推导分辨率，优先查映射表，否则按 16:9 从高度推算"""
    if qn in BILI_RESOLUTION_MAP:
        return BILI_RESOLUTION_MAP[qn]
    if fallback_height > 0:
        w = int(fallback_height * 16 / 9)
        return f"{w}x{fallback_height}"
    return ""


def _get_filesize_for_qn(qn: int, durl_size: int, duration_seconds: int) -> str:
    """获取清晰度对应的文件大小：优先用 durl size，否则按典型码率估算"""
    from app.services.download.base import BaseDownloader
    if durl_size and durl_size > 0:
        return BaseDownloader.calculate_filesize(filesize_bytes=durl_size)
    bitrate = _QUALITY_BITRATE_MAP.get(qn)
    if bitrate and duration_seconds > 0:
        return BaseDownloader.calculate_filesize(bitrate_bps=bitrate, duration_seconds=duration_seconds)
    return "未知"


def extract_account_info_from_cookie(cookie_str: str) -> dict:
    """从B站Cookie中提取账号信息
    
    Args:
        cookie_str: Cookie字符串（支持Netscape格式或原始格式）
    
    Returns:
        dict: 包含 account_id, account_name, account_avatar, account_url
    """
    info = {
        "account_id": None,
        "account_name": None,
        "account_avatar": None,
        "account_url": None,
    }
    
    try:
        # 将Netscape格式的Cookie转换成原始格式
        mgr = CookieManager()
        raw_cookie = mgr.extract_raw(cookie_str)
        
        with httpx.Client(timeout=30) as client:
            headers = {
                "Cookie": raw_cookie or cookie_str,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            }
            logger.info(f"[Bilibili] Extracting account info from cookie")
            resp = client.get("https://api.bilibili.com/x/web-interface/nav", headers=headers)
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0:
                    data = result.get("data", {})
                    if data.get("isLogin"):
                        info["account_id"] = str(data.get("mid", ""))
                        info["account_name"] = data.get("uname", "")
                        info["account_avatar"] = data.get("face", "")
                        info["account_url"] = f"https://space.bilibili.com/{info['account_id']}"
                        logger.info(f"[Bilibili] Extracted account: {info['account_name']} (ID: {info['account_id']})")
    
    except Exception as e:
        logger.warning(f"[Bilibili] Failed to extract account info: {e}")
    
    return info
