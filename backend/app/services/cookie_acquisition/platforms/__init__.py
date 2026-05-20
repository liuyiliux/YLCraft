"""
YLCraft — 平台适配器注册

提供统一的适配器获取接口
"""

from __future__ import annotations

from typing import Optional

from app.services.cookie_acquisition.base import PlatformDetector, QrcodeAdapter, get_platform_domains as _get_platform_domains


def get_platform_domains(platform: str) -> str:
    """获取平台的关联域名列表（委托给 base.py）"""
    return _get_platform_domains(platform)
_detector_registry: dict[str, str] = {
    "xhs": "app.services.cookie_acquisition.platforms.xiaohongshu:XhsDetector",
    "douyin": "app.services.cookie_acquisition.platforms.douyin:DouyinDetector",
    "kuaishou": "app.services.cookie_acquisition.platforms.kuaishou:KuaishouDetector",
    "bilibili": "app.services.cookie_acquisition.platforms.bilibili:BilibiliDetector",
    "weibo": "app.services.cookie_acquisition.platforms.weibo:WeiboDetector",
    "zhihu": "app.services.cookie_acquisition.platforms.zhihu:ZhihuDetector",
}

_qrcode_registry: dict[str, str] = {
    "bilibili": "app.services.cookie_acquisition.platforms.bilibili:BilibiliQrcodeAdapter",
    # 其他平台二维码适配器预留
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


def get_supported_patchright_platforms() -> list[str]:
    """获取支持 Playwright 获取的平台列表"""
    return list(_detector_registry.keys())


def get_supported_qrcode_platforms() -> list[str]:
    """获取支持二维码获取的平台列表"""
    return list(_qrcode_registry.keys())
