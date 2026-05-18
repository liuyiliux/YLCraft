"""
统一 Cookie 管理器

提供跨平台 Cookie 的统一存储和读取接口
规范：只使用 cookie_content(Netscape格式) 存储，credentials 只作为备份
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

logger = logging.getLogger("ylcraft.cookie_manager")


class CookieManager:
    """
    统一 Cookie 管理器

    存储规范：
    - cookie_content: Netscape 格式（唯一存储位置）
    - credentials.raw: 原始格式备份（可选）
    - credentials.source: 来源标记 manual/playwright/qrcode
    """

    # 各平台默认域名
    PLATFORM_DOMAINS = {
        "bilibili": ".bilibili.com,.bangumi.bilibili.com,.b23.tv",
        "douyin": ".douyin.com,.iesdouyin.com,.amemv.com",
        "kuaishou": ".kuaishou.com,.kuaishoup.com",
        "xhs": ".xiaohongshu.com,.xhscdn.com",
        "weibo": ".weibo.com,.sina.com.cn",
        "zhihu": ".zhihu.com",
        "youtube": ".youtube.com,.googlevideo.com",
        "tiktok": ".tiktok.com",
        "twitter": ".twitter.com,.x.com",
    }

    def __init__(self, platform: str):
        self.platform = platform.lower()
        self.default_domains = self.PLATFORM_DOMAINS.get(self.platform, ".example.com")

    def parse_cookie(self, cookie_str: str, domains: str = "") -> str:
        """
        解析任意格式的 Cookie，统一转为 Netscape 格式

        支持格式：
        1. Netscape 格式（直接返回）
        2. JSON 数组格式 [{"name":"a","value":"1"},...]
        3. 原始字符串 "key=value; key2=value2"

        Args:
            cookie_str: 原始 cookie 字符串
            domains: 域名列表（逗号分隔），用于 raw 格式转换

        Returns:
            Netscape 格式 cookie 字符串
        """
        if not cookie_str:
            return ""

        cookie_str = cookie_str.strip()

        # 1. 已经是 Netscape 格式
        if cookie_str.startswith("# Netscape HTTP Cookie File"):
            return self._clean_netscape(cookie_str)

        # 2. JSON 数组格式
        if cookie_str.startswith("[") or cookie_str.startswith("{"):
            return self._json_to_netscape(cookie_str, domains)

        # 3. 原始字符串格式
        return self._raw_to_netscape(cookie_str, domains)

    def extract_raw(self, cookie_content: str) -> str:
        """
        从 Netscape 格式提取原始 cookie 字符串

        Args:
            cookie_content: Netscape 格式 cookie

        Returns:
            原始格式 "key=value; key2=value2"
        """
        if not cookie_content:
            return ""

        parts = []
        for line in cookie_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) >= 7:
                name = fields[5]
                value = fields[6]
                parts.append(f"{name}={value}")

        return "; ".join(parts)

    def _clean_netscape(self, content: str) -> str:
        """清洗 Netscape 格式，确保格式正确"""
        lines = ["# Netscape HTTP Cookie File", ""]
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) >= 7:
                lines.append(line)
        return "\n".join(lines)

    def _json_to_netscape(self, json_str: str, domains: str = "") -> str:
        """JSON 格式转为 Netscape"""
        import json

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return self._raw_to_netscape(json_str, domains)

        lines = ["# Netscape HTTP Cookie File", ""]

        # 处理数组格式
        if isinstance(data, list):
            for c in data:
                self._add_cookie_line(lines, c, domains)
        # 处理对象格式
        elif isinstance(data, dict):
            self._add_cookie_line(lines, data, domains)

        return "\n".join(lines)

    def _add_cookie_line(self, lines: list, c: dict, domains: str):
        """添加一条 cookie 到 lines"""
        name = c.get("name", "")
        value = c.get("value", "")
        if not name:
            return

        domain = c.get("domain", "")
        if not domain:
            domain = domains.split(",")[0].strip() if domains else self.default_domains.split(",")[0]

        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", True) else "FALSE"
        expires = c.get("expires", -1)
        if expires == -1:
            expires = int(time.time()) + 86400 * 365
        else:
            expires = int(expires)

        is_dot = "TRUE" if domain.startswith(".") else "FALSE"
        lines.append(f"{domain}\t{is_dot}\t{path}\t{secure}\t{expires}\t{name}\t{value}")

    def _raw_to_netscape(self, raw: str, domains: str = "") -> str:
        """原始字符串格式转为 Netscape"""
        lines = ["# Netscape HTTP Cookie File", ""]
        default_domain = domains.split(",")[0].strip() if domains else self.default_domains.split(",")[0]
        if default_domain and not default_domain.startswith("."):
            default_domain = "." + default_domain

        default_expires = str(int(time.time()) + 86400 * 365)
        is_dot = "TRUE" if default_domain.startswith(".") else "FALSE"

        pair_pattern = re.compile(r"([^=;]+?)\s*=\s*(\"[^\"]*\"|[^;]*)")
        for m in pair_pattern.finditer(raw):
            name = m.group(1).strip()
            value = m.group(2).strip()
            if not name:
                continue
            # 去除引号
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1]
            lines.append(f"{default_domain}\t{is_dot}\t/\tFALSE\t{default_expires}\t{name}\t{value}")

        return "\n".join(lines)

    def validate(self, cookie_content: str) -> dict:
        """
        验证 cookie 有效性

        Returns:
            {"valid": bool, "count": int, "message": str}
        """
        if not cookie_content:
            return {"valid": False, "count": 0, "message": "Cookie 为空"}

        # 尝试解析
        parsed = self.parse_cookie(cookie_content)
        if not parsed:
            return {"valid": False, "count": 0, "message": "无法解析为有效格式"}

        # 统计条数
        count = 0
        for line in parsed.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                count += 1

        if count == 0:
            return {"valid": False, "count": 0, "message": "没有有效的 Cookie 条目"}

        return {"valid": True, "count": count, "message": f"有效，共 {count} 条"}


# 全局缓存（按平台）
_cookie_managers: dict[str, CookieManager] = {}


def get_cookie_manager(platform: str = "generic") -> CookieManager:
    """获取 Cookie 管理器实例"""
    platform = platform.lower()
    if platform not in _cookie_managers:
        _cookie_managers[platform] = CookieManager(platform)
    return _cookie_managers[platform]


def parse_cookie_to_netscape(cookie_str: str, platform: str = "generic", domains: str = "") -> str:
    """
    快捷函数：将任意格式 cookie 转为 Netscape 格式

    Args:
        cookie_str: 原始 cookie 字符串
        platform: 平台名称
        domains: 域名列表

    Returns:
        Netscape 格式字符串
    """
    mgr = get_cookie_manager(platform)
    return mgr.parse_cookie(cookie_str, domains)


def extract_raw_cookie(netscape_content: str) -> str:
    """
    快捷函数：从 Netscape 格式提取原始字符串

    Args:
        netscape_content: Netscape 格式 cookie

    Returns:
        原始格式 "key=value; key2=value2"
    """
    mgr = get_cookie_manager("generic")
    return mgr.extract_raw(netscape_content)
