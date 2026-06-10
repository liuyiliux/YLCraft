"""Shared browser automation services."""

from app.services.browser.patchright_runtime import (
    BrowserFetchResult,
    PATCHRIGHT_INSTALL_MESSAGE,
    PatchrightBrowserRuntime,
    cookie_header_to_browser_cookies,
    get_patchright_runtime,
)
from app.services.browser.visible_session import (
    VisibleBrowserSessionManager,
    get_visible_browser_session_manager,
)

__all__ = [
    "BrowserFetchResult",
    "PATCHRIGHT_INSTALL_MESSAGE",
    "PatchrightBrowserRuntime",
    "cookie_header_to_browser_cookies",
    "get_patchright_runtime",
    "VisibleBrowserSessionManager",
    "get_visible_browser_session_manager",
]
