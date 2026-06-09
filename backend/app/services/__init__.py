"""YLCraft — 业务服务层."""

from __future__ import annotations


def get_services_info() -> dict:
    """Return a compact description of the service layer."""
    return {
        "name": "YLCraft services",
        "layer": "business",
        "packages": [
            "ai",
            "asset",
            "breaker",
            "crawler",
            "platform_connection",
            "platforms",
        ],
    }


__all__ = ["get_services_info"]
