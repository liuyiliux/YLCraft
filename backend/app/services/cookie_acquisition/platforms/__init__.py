"""
YLCraft — 平台适配器注册

提供统一的适配器获取接口
"""

from __future__ import annotations

from typing import Optional

from app.services.cookie_acquisition.base import PlatformDetector, QrcodeAdapter

# 适配器注册表（懒加载）
_detector_registry: dict[str, str] = {
    "xhs": "app.services.cookie_acquisition.platforms.xiaohongshu:XhsDetector",
    "douyin": "app.services.cookie_acquisition.platforms.douyin:DouyinDetector",
    "kuaishou": "app.services.cookie_acquisition.platforms.kuaishou:KuaishouDetector",
    "bilibili": "app.services.cookie_acquisition.platforms.bilibili:BilibiliDetector",
    "weibo": "app.services.cookie_acquisition.platforms.weibo:WeiboDetector",
    "zhihu": "app.services.cookie_acquisition.platforms.zhihu:ZhihuDetector",
}

_qrcode_registry: dict[str, str] = {
    # 二维码适配器暂未实现，预留接口
}

# 已加载的实例缓存
_detector_cache: dict[str, PlatformDetector] = {}
_qrcode_cache: dict[str, QrcodeAdapter] = {}


def _import_class(path: str):
    """动态导入类"""
    module_path, class_name = path.rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_detector(platform: str) -> Optional[PlatformDetector]:
    """获取平台登录检测器"""
    if platform in _detector_cache:
        return _detector_cache[platform]

    path = _detector_registry.get(platform)
    if not path:
        return None

    try:
        cls = _import_class(path)
        instance = cls()
        _detector_cache[platform] = instance
        return instance
    except Exception as e:
        import logging
        logging.getLogger("ylcraft.cookie_acquisition.platforms").warning(
            f"Failed to load detector for {platform}: {e}"
        )
        return None


def get_qrcode_adapter(platform: str) -> Optional[QrcodeAdapter]:
    """获取平台二维码适配器"""
    if platform in _qrcode_cache:
        return _qrcode_cache[platform]

    path = _qrcode_registry.get(platform)
    if not path:
        return None

    try:
        cls = _import_class(path)
        instance = cls()
        _qrcode_cache[platform] = instance
        return instance
    except Exception as e:
        import logging
        logging.getLogger("ylcraft.cookie_acquisition.platforms").warning(
            f"Failed to load qrcode adapter for {platform}: {e}"
        )
        return None


def get_supported_playwright_platforms() -> list[str]:
    """获取支持 Playwright 获取的平台列表"""
    return list(_detector_registry.keys())


def get_supported_qrcode_platforms() -> list[str]:
    """获取支持二维码获取的平台列表"""
    return list(_qrcode_registry.keys())


# =============================================================================
# 平台域名映射（用于 Cookie 保存时设置 domains 字段）
# =============================================================================

PLATFORM_DOMAINS = {
    "douyin": ".douyin.com,.iesdouyin.com,v.douyin.com",
    "tiktok": ".tiktok.com",
    "kuaishou": ".kuaishou.com,.gifshow.com,v.kuaishou.com",
    "bilibili": ".bilibili.com,b23.tv",
    "xiaohongshu": ".xiaohongshu.com,xhslink.com",
    "xhs": ".xiaohongshu.com,xhslink.com",
    "weibo": ".weibo.com,t.cn",
    "zhihu": ".zhihu.com",
    "youtube": ".youtube.com,youtu.be",
    "twitter": ".twitter.com,.x.com,t.co,pbs.twimg.com,abs.twimg.com",
    "telegram": ".telegram.org,t.me,web.telegram.org",
}


def get_platform_domains(platform: str) -> str:
    """获取平台的关联域名列表"""
    return PLATFORM_DOMAINS.get(platform, "")
