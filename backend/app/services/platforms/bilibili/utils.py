"""
YLCraft — B站工具函数

包含B站相关的辅助功能，如Cookie解析、账号信息提取等
"""

import logging
import httpx

from app.services.cookies.manager import CookieManager

logger = logging.getLogger("ylcraft.platforms.bilibili.utils")


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
        mgr = CookieManager("bilibili")
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
