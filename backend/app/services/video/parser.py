"""YLCraft — 视频解析模块

统一使用 yt-dlp 解析所有平台（支持 1000+ 网站）。
支持平台：抖音/快手/B站/小红书/微博/YouTube/TikTok 等。

抖音特殊说明（iesdouyin.com 方案）：
- 抖音桌面端 API 需要 msToken HttpOnly Cookie，
  无法通过浏览器插件导出，改用移动端 iesdouyin.com/share/video/{id}/ 页面方案。
- 该页面 HTML 中嵌入 window._ROUTER_DATA JSON，完全无需 Cookie 即可解析。
- 参考：yby6-video-parser skill 的 douyin.py 实现。
"""

from __future__ import annotations

from .parsers import parse_twitter_syndication
import asyncio
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import time
import httpx
from urllib.parse import urlparse, urlunparse, unquote

logger = logging.getLogger("ylcraft.parser")


def _find_ytdlp() -> str:
    """查找 yt-dlp 可执行文件路径（跨平台：venv_win/venv_linux/venv + PATH 兜底）"""
    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    # 按优先级尝试
    candidates = [
        backend_dir / "venv_win" / "Scripts" / "yt-dlp.exe",
        backend_dir / "venv_linux" / "bin" / "yt-dlp",
        backend_dir / "venv" / "Scripts" / "yt-dlp.exe",
        backend_dir / "venv" / "bin" / "yt-dlp",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # PATH 兜底
    which = shutil.which("yt-dlp.exe") or shutil.which("yt-dlp")
    if which:
        return which
    raise FileNotFoundError("yt-dlp not found in any venv or PATH")


# =============================================================================
# Cookie 管理
# =============================================================================

class CookieManager:
    """
    Cookie 管理器。
    Cookie 数据完全存储在 PlatformConnection 表中，直接通过内存传递给 yt-dlp，无需任何本地文件！
    
    统一凭证架构：从 PlatformConnection 唯一存储读取 Cookie
    - cookie_content (Netscape 格式) → yt-dlp 直接使用
    - credentials (JSON) → 自动转换为 Netscape 格式
    """

    def __init__(self):
        # 确保持久 Cookie 目录存在
        self._ensure_cookie_dir()

    def _get_cookie_dir(self) -> Path:
        """持久 Cookie 文件目录（backend/data/cookies/）"""
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent
        return backend_dir / "data" / "cookies"

    def _ensure_cookie_dir(self):
        """确保持久 Cookie 目录存在"""
        self._get_cookie_dir().mkdir(parents=True, exist_ok=True)

    def _get_cookie_file_path(self, platform: str) -> Path:
        """获取持久 Cookie 文件路径（固定，每次保存时覆盖）"""
        return self._get_cookie_dir() / f"{platform}.txt"

    def _get_db_session(self):
        """获取数据库 session"""
        from app.db.database import SessionLocal
        return SessionLocal()

    def _get_domain_from_url(self, url: str) -> str:
        """从 URL 提取纯域名"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.lower()

    def _match_platform_for_url(self, url: str):
        """从 PlatformConnection 统一凭证表中，通过关联域名列表匹配最合适的平台
        
        返回一个具有 cookie_content / domains / name 属性的对象。
        """
        url_domain = self._get_domain_from_url(url)
        if not url_domain:
            return None
        
        session = self._get_db_session()
        try:
            from app.db.models.platform_connection import (
                PlatformConnection, AuthType, ConnectionStatus
            )
            # 从 PlatformConnection（唯一凭证存储）读取
            platforms = session.query(PlatformConnection).filter(
                PlatformConnection.auth_type == AuthType.COOKIE,
                PlatformConnection.cookie_content != None,
                PlatformConnection.cookie_content != "",
            ).all()
            
            # 按域名匹配度排序（最长匹配优先）
            matched = []
            for conn in platforms:
                if not conn.domains:
                    continue
                domains_list = [d.strip().lower() for d in conn.domains.split(",") if d.strip()]
                for d in domains_list:
                    if d.startswith('.'):
                        pure_domain = d[1:]
                        if url_domain == pure_domain or url_domain.endswith('.' + pure_domain):
                            matched.append((len(d), conn))
                    else:
                        if d in url_domain or url_domain.endswith('.' + d):
                            matched.append((len(d), conn))
            
            if matched:
                matched.sort(key=lambda x: -x[0])
                return matched[0][1]
            return None
        except Exception as e:
            logger.warning(f"[CookieManager] 平台域名匹配失败: {e}")
            return None
        finally:
            session.close()

    def _clean_netscape_content(self, content: str) -> str:
        """
        清洗 Netscape Cookie 文件内容：
        - 去掉值两端的引号（浏览器导出时常带引号）
        - 不做 URL 解码！Cookie 值里的 %3A / %3D 是字面量，解码会改变实际值
        """
        lines = content.splitlines()
        cleaned = []
        for line in lines:
            if not line.strip() or line.strip().startswith('#'):
                cleaned.append(line)
                continue
            parts = line.split('\t')
            if len(parts) >= 7:
                value = '\t'.join(parts[6:])
                # 只去掉值两端的引号（浏览器 JSON 导出时会加引号）
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                # 【关键】不做 unquote！Cookie 值里的 %3A 是字面量
                parts = parts[:6] + [value]
                cleaned.append('\t'.join(parts))
            else:
                cleaned.append(line)
        return '\n'.join(cleaned)

    def _convert_to_netscape(self, platform: str, cookie_content: str) -> str:
        """
        将 Cookie 内容转换为 Netscape 格式。
        支持三种输入：
        1. 已为 Netscape 格式（# Netscape HTTP Cookie File 开头）
        2. JSON 数组格式（浏览器扩展导出）
        3. key=value; key2="value2" 字符串格式（DevTools 复制）
        """
        cookie_content = cookie_content.strip()

        # 格式1：已经是 Netscape 格式
        if cookie_content.startswith("# Netscape HTTP Cookie File"):
            return self._clean_netscape_content(cookie_content)

        # 获取平台默认域名（从 PlatformConnection 的 domains 字段）
        default_domain = ".example.com"
        try:
            session = self._get_db_session()
            from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType
            # 尝试通过 platform 枚举匹配
            try:
                plat_enum = PlatformType(platform)
                conn = session.query(PlatformConnection).filter(
                    PlatformConnection.platform == plat_enum,
                    PlatformConnection.auth_type == AuthType.COOKIE,
                ).first()
                if conn and conn.domains:
                    d = conn.domains.split(",")[0].strip()
                    if d:
                        default_domain = d if d.startswith(".") else "." + d
            except ValueError:
                pass
            session.close()
        except Exception:
            pass

        # 格式2：JSON 数组格式
        try:
            data = json.loads(cookie_content)
            if isinstance(data, list) and len(data) > 0:
                lines = ["# Netscape HTTP Cookie File", ""]
                for c in data:
                    name = str(c.get("name", "")).strip()
                    value = str(c.get("value", ""))
                    if not name:
                        continue
                    # 去掉 JSON 导出时值两端的引号
                    value = value.strip()
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    # URL 解码
                    try:
                        value = unquote(value)
                    except Exception:
                        pass
                    domain = str(c.get("domain", "")).strip()
                    if not domain:
                        domain = default_domain
                    elif not domain.startswith("."):
                        domain = "." + domain
                    path_val = str(c.get("path", "/")) or "/"
                    secure = "TRUE" if c.get("secure", True) else "FALSE"
                    # 过期时间
                    exp = c.get("expirationDate") or c.get("expires")
                    if exp is None:
                        exp = int(time.time()) + 86400 * 365
                    else:
                        exp = int(float(exp))
                    is_dot = "TRUE" if domain.startswith(".") else "FALSE"
                    lines.append(f"{domain}\t{is_dot}\t{path_val}\t{secure}\t{exp}\t{name}\t{value}")
                return "\n".join(lines)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        # 格式3：key=value; key2="value2" 字符串格式（DevTools 复制）
        lines = ["# Netscape HTTP Cookie File", ""]
        default_expires = str(int(time.time()) + 86400 * 365)
        is_dot = "TRUE" if default_domain.startswith(".") else "FALSE"

        # 去掉可能的 "Cookie: " 前缀（从 Network 面板复制时会带）
        if cookie_content.lower().startswith("cookie:"):
            cookie_content = cookie_content[cookie_content.find(":")+1:].strip()

        # 按分号分割，处理每个 key=value
        # 注意：值里可能有分号（如 JSON），但 DevTools 复制的格式通常不会
        # 更健壮的方式：用正则逐对匹配
        # 匹配 key=value（值可能带引号，可能包含特殊字符直到分号或结尾）
        pair_pattern = re.compile(r'([^=;]+?)\s*=\s*("[^"]*"|[^;]*)')
        for m in pair_pattern.finditer(cookie_content):
            name = m.group(1).strip()
            value = m.group(2).strip()
            if not name:
                continue
            # 去掉值两端的引号
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1]
            # URL 解码【注意】不能对 Cookie 值做 unquote！
            # 浏览器 Cookie 头里的 %3A 是字面量，不是编码
            # 如果原始值确实需要解码，应该在导出时处理，而不是在这里
            pass  # 故意留空，不做 unquote
            lines.append(f"{default_domain}\t{is_dot}\t/\tFALSE\t{default_expires}\t{name}\t{value}")

        if len(lines) > 2:
            return "\n".join(lines)

        return cookie_content

    def save_cookie(self, platform: str, cookie_content: str) -> bool:
        """保存 Cookie 到 PlatformConnection 统一凭证表 + 同步写入持久 Cookie 文件"""
        session = self._get_db_session()
        try:
            from app.db.models.platform_connection import (
                PlatformConnection, PlatformType, AuthType, AcquisitionMethod, ConnectionStatus
            )
            netscape_content = self._convert_to_netscape(platform, cookie_content)
            
            # 尝试匹配 platform 枚举
            try:
                plat_enum = PlatformType(platform)
            except ValueError:
                plat_enum = None
            
            # 查找该平台是否已有 Cookie 类型连接
            if plat_enum:
                existing = session.query(PlatformConnection).filter(
                    PlatformConnection.platform == plat_enum,
                    PlatformConnection.auth_type == AuthType.COOKIE,
                ).first()
            else:
                existing = None
            
            if existing:
                existing.cookie_content = netscape_content
                existing.acquisition_method = AcquisitionMethod.MANUAL
                # 同时更新 credentials
                creds = existing.get_credentials()
                creds["raw"] = self._netscape_to_raw(netscape_content)
                creds["source"] = "manual"
                existing.set_credentials(creds)
                existing.update_timestamp()
            else:
                # 创建新的 PlatformConnection
                if not plat_enum:
                    logger.warning(f"[CookieManager] 未知平台 {platform}，无法创建 PlatformConnection")
                    return False
                conn = PlatformConnection(
                    id=str(__import__('uuid').uuid4()),
                    platform=plat_enum,
                    name=f"{platform} Cookie",
                    auth_type=AuthType.COOKIE,
                    status=ConnectionStatus.UNKNOWN,
                    cookie_content=netscape_content,
                    acquisition_method=AcquisitionMethod.MANUAL,
                )
                creds = {"raw": self._netscape_to_raw(netscape_content), "source": "manual"}
                conn.set_credentials(creds)
                # 设置默认域名
                from app.services.cookie_acquisition.platforms import get_platform_domains
                domains = get_platform_domains(platform)
                if domains:
                    conn.domains = domains
                session.add(conn)
            
            session.commit()
            
            # 同步写入持久 Cookie 文件
            clean_content = self._clean_netscape_content(netscape_content)
            cookie_path = self._get_cookie_file_path(platform)
            cookie_path.write_text(clean_content, encoding="utf-8")
            cookie_path.chmod(0o600)
            logger.info(f"[CookieManager] 保存 {platform} Cookie → PlatformConnection + 持久文件 {cookie_path}")
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _netscape_to_raw(cookie_content: str) -> str:
        """从 Netscape 格式提取 raw 字符串"""
        parts = []
        for line in cookie_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            if len(fields) >= 7:
                parts.append(f"{fields[5]}={fields[6]}")
        return "; ".join(parts)

    def delete_cookie(self, platform: str) -> bool:
        """从 PlatformConnection 清空 Cookie + 删除持久文件"""
        session = self._get_db_session()
        try:
            from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType
            try:
                plat_enum = PlatformType(platform)
                existing = session.query(PlatformConnection).filter(
                    PlatformConnection.platform == plat_enum,
                    PlatformConnection.auth_type == AuthType.COOKIE,
                ).first()
            except ValueError:
                existing = None
            if existing:
                existing.cookie_content = None
                existing.update_timestamp()
                session.commit()
            # 删除持久文件
            cookie_path = self._get_cookie_file_path(platform)
            if cookie_path.exists():
                cookie_path.unlink()
                logger.info(f"[CookieManager] 已删除持久文件 {cookie_path}")
            logger.info(f"[CookieManager] 已清空 {platform} Cookie")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"[CookieManager] 删除 {platform} Cookie 失败: {e}")
            return False
        finally:
            session.close()

    def list_cookies(self) -> dict[str, dict]:
        """列出所有平台 Cookie 状态（从 PlatformConnection 统一凭证表读取）"""
        session = self._get_db_session()
        try:
            from app.db.models.platform_connection import PlatformConnection, AuthType
            platforms = session.query(PlatformConnection).filter(
                PlatformConnection.auth_type == AuthType.COOKIE,
            ).all()
            result = {}
            for conn in platforms:
                plat_id = conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform)
                result[plat_id] = {
                    "size": len(conn.cookie_content) if conn.cookie_content else 0,
                    "modified": conn.updated_at.timestamp() if conn.updated_at else 0,
                    "display_name": conn.name,
                    "has_cookie": bool(conn.cookie_content),
                    "domains": conn.domains or "",
                    "test_url": conn.test_url or "",
                    "description": conn.description or "",
                }
            return result
        except Exception as e:
            logger.error(f"[CookieManager] 列出 Cookie 失败: {e}")
            return {}
        finally:
            session.close()

    def get_cookiejar_for_url(self, url: str):
        """从 URL 智能匹配平台（通过多域名别名），返回 yt-dlp 的 YoutubeDLCookieJar 对象（完全内存操作）"""
        conn = self._match_platform_for_url(url)
        if not conn or not conn.cookie_content:
            return None
        try:
            from io import StringIO
            from yt_dlp.cookies import YoutubeDLCookieJar
            clean_content = self._clean_netscape_content(conn.cookie_content)
            # 调试：脱敏打印 Netscape Cookie 内容（只显示 name 和 value 前3字符）
            debug_lines = []
            for line in clean_content.splitlines():
                if line.strip() and not line.strip().startswith('#'):
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        name = parts[5]
                        val = parts[6]
                        val_preview = val[:3] + "..." if len(val) > 3 else val
                        debug_lines.append(f"  {name}={val_preview}")
            if debug_lines:
                logger.info(f"[CookieManager] Cookie 内容预览（脱敏）:\n" + "\n".join(debug_lines))
            else:
                logger.info("[CookieManager] Cookie 内容预览（脱敏）: 无有效Cookie行")
            jar = YoutubeDLCookieJar()
            jar.load(StringIO(clean_content))
            display_name = conn.name if hasattr(conn, 'name') else str(conn.platform)
            logger.info(f"[CookieManager] 从内存加载了平台 [{display_name}] Cookie 给 yt-dlp，共 {len(jar)} 个 Cookie")
            return jar
        except Exception as e:
            logger.warning(f"[CookieManager] 解析 Cookie 失败: {e}")
            return None

    def get_platform_info(self, platform: str) -> Optional[dict]:
        """获取平台配置信息（从 PlatformConnection 统一凭证表读取）"""
        session = self._get_db_session()
        try:
            from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType
            try:
                plat_enum = PlatformType(platform)
                conn = session.query(PlatformConnection).filter(
                    PlatformConnection.platform == plat_enum,
                    PlatformConnection.auth_type == AuthType.COOKIE,
                ).first()
            except ValueError:
                conn = None
            if conn:
                return {
                    "id": conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform),
                    "display_name": conn.name,
                    "domains": conn.domains or "",
                    "test_url": conn.test_url or "",
                    "has_cookie": bool(conn.cookie_content),
                    "description": conn.description or "",
                }
            return None
        except Exception:
            return None
        finally:
            session.close()
    
    def get_cookie_path_for_url(self, url: str) -> Optional[str]:
        """返回持久 Cookie 文件路径给 yt-dlp 子进程（固定文件，每次保存时自动更新）"""
        conn = self._match_platform_for_url(url)
        if not conn or not conn.cookie_content:
            return None
        try:
            plat_id = conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform)
            cookie_path = self._get_cookie_file_path(plat_id)
            # 如果文件不存在但 DB 有内容，写入文件
            if not cookie_path.exists():
                clean_content = self._clean_netscape_content(conn.cookie_content)
                cookie_path.write_text(clean_content, encoding="utf-8")
                cookie_path.chmod(0o600)
                logger.info(f"[CookieManager] 从数据库同步写入持久Cookie文件: {cookie_path.name}")
            logger.info(f"[CookieManager] 使用持久 Cookie 文件: {cookie_path.name}")
            return str(cookie_path)
        except Exception as e:
            logger.warning(f"[CookieManager] 获取 Cookie 文件路径失败: {e}")
            return None

    def save_platform(self, platform_id: str, display_name: str, domains: str = "", test_url: str = "", description: str = "") -> bool:
        """保存/更新平台配置到 PlatformConnection（支持逗号分隔多域名别名）"""
        session = self._get_db_session()
        try:
            from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType, ConnectionStatus
            try:
                plat_enum = PlatformType(platform_id)
            except ValueError:
                logger.warning(f"[CookieManager] 未知平台 {platform_id}，无法保存配置")
                return False
            
            existing = session.query(PlatformConnection).filter(
                PlatformConnection.platform == plat_enum,
                PlatformConnection.auth_type == AuthType.COOKIE,
            ).first()
            if existing:
                existing.name = display_name
                if domains:
                    existing.domains = domains
                if test_url:
                    existing.test_url = test_url
                if description:
                    existing.description = description
                existing.update_timestamp()
            else:
                conn = PlatformConnection(
                    id=str(__import__('uuid').uuid4()),
                    platform=plat_enum,
                    name=display_name,
                    auth_type=AuthType.COOKIE,
                    status=ConnectionStatus.UNKNOWN,
                    domains=domains,
                    test_url=test_url,
                    description=description,
                )
                session.add(conn)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"[CookieManager] 保存平台 {platform_id} 失败: {e}")
            return False
        finally:
            session.close()

    def delete_platform(self, platform: str) -> bool:
        """删除平台配置（Cookie 数据 + 平台配置）"""
        session = self._get_db_session()
        try:
            from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType
            try:
                plat_enum = PlatformType(platform)
                existing = session.query(PlatformConnection).filter(
                    PlatformConnection.platform == plat_enum,
                    PlatformConnection.auth_type == AuthType.COOKIE,
                ).first()
            except ValueError:
                existing = None
            if existing:
                session.delete(existing)
                session.commit()
                logger.info(f"[CookieManager] 已删除平台 {platform}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"[CookieManager] 删除平台 {platform} 失败: {e}")
            return False
        finally:
            session.close()


_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class VideoInfo:
    """解析后的视频信息（统一格式）"""
    original_url: str
    platform: str = ""

    video_url: str = ""
    audio_url: str = ""
    cover_url: str = ""
    images: list = field(default_factory=list)

    title: str = ""
    desc: str = ""
    author_name: str = ""
    author_uid: str = ""
    author_avatar: str = ""
    duration: int = 0
    width: int = 0
    height: int = 0

    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    play_count: int = 0

    content_type: str = "video"
    qualities: list = field(default_factory=list)
    parse_method: str = ""
    raw: dict = field(default_factory=dict)

    def is_valid(self) -> bool:
        return bool(self.video_url) or bool(self.images)


# =============================================================================
# 通用工具
# =============================================================================

def _normalize_twitter_url(url: str) -> str:
    """
    Twitter URL 规范化处理
    将各种格式的 Twitter/X 链接统一转换为 yt-dlp 友好的标准格式
    支持：
    - /i/status/12345 → 转为 https://x.com/i/status/12345 (yt-dlp 支持)
    - t.co 短链接展开
    - pic.twitter.com 图片链接处理
    - 其他异常格式修复
    """
    from urllib.parse import urlparse, urlunparse
    
    # 第一步：深度清理 URL 脏字符（去除前后多余的反引号、逗号、空格、引号等）
    import re
    url = url.strip()
    # 用正则去掉前后所有非 URL 合法字符
    url = re.sub(r'^[`\'",\s]+', '', url)
    url = re.sub(r'[`\'",\s]+$', '', url)
    url_lower = url.lower()
    
    # 方案1: 直接检测并规范化 /i/status/ 短链接格式
    # 例如: https://twitter.com/i/status/12345 或 https://x.com/i/status/12345
    i_status_match = re.search(r'/(?:i|intent)/status/(\d+)', url_lower)
    if i_status_match:
        tweet_id = i_status_match.group(1)
        # 优先使用 x.com 作为域名，yt-dlp 最新 Twitter 提取器默认支持 x.com
        normalized = f"https://x.com/i/status/{tweet_id}"
        logger.info(f"[Twitter URL 规范化] 将 {url} → {normalized}")
        return normalized
    
    # 方案2: 提取纯推文 ID 并构造标准 URL
    tweet_id_match = re.search(r'(?:status|statuses)/(\d+)', url_lower)
    if tweet_id_match:
        tweet_id = tweet_id_match.group(1)
        # 提取原 URL 中的用户名（可选），如果没有就用 /i/status/ 格式
        username_match = re.search(r'/(?:@|x\.com|twitter\.com)/([a-zA-Z0-9_]+)/status/', url_lower)
        if username_match:
            username = username_match.group(1)
            normalized = f"https://x.com/{username}/status/{tweet_id}"
            logger.info(f"[Twitter URL 规范化] 将 {url} → {normalized}")
            return normalized
        else:
            normalized = f"https://x.com/i/status/{tweet_id}"
            logger.info(f"[Twitter URL 规范化] 将 {url} → {normalized}")
            return normalized
    
    return url


def _detect_platform(url: str) -> str:
    """从 URL 检测平台"""
    url_lower = url.lower()
    if any(x in url_lower for x in ["douyin.com", "iesdouyin.com", "v.douyin"]):
        return "douyin"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if any(x in url_lower for x in ["kuaishou.com", "gifshow.com", "v.kuaishou"]):
        return "kuaishou"
    if any(x in url_lower for x in ["bilibili.com", "b23.tv"]):
        return "bilibili"
    if any(x in url_lower for x in ["xiaohongshu.com", "xhslink.com"]):
        return "xiaohongshu"
    if any(x in url_lower for x in ["weibo.com", "t.cn"]):
        return "weibo"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if any(x in url_lower for x in ["twitter.com", "x.com", "t.co", "pic.twitter.com"]):
        return "twitter"
    if any(x in url_lower for x in ["telegram.org", "t.me", "web.telegram.org"]):
        return "telegram"
    return "unknown"


def _extract_url_from_text(text: str) -> str:
    """从分享文本中提取 URL"""
    pattern = r"https?://[^\s\u4e00-\u9fff]+"
    matches = re.findall(pattern, text)
    if matches:
        preferred_domains = [
            "v.douyin.com", "iesdouyin.com", "douyin.com",
            "v.kuaishou.com", "kuaishou.com",
            "b23.tv", "bilibili.com",
            "xhslink.com", "xiaohongshu.com",
            "t.cn", "weibo.com",
        ]
        for domain in preferred_domains:
            for url in matches:
                if domain in url:
                    return url
        return matches[0]
    return text.strip()


def _ytdlp_best_url(data: dict) -> str:
    """从 yt-dlp 数据中选择最佳视频 URL"""
    if data.get("url"):
        return data["url"]
    formats = data.get("formats", [])
    if not formats:
        return ""
    video_fmts = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
    if not video_fmts:
        for f in reversed(formats):
            if f.get("url"):
                return f["url"]
        return ""
    mp4_fmts = [f for f in video_fmts if f.get("ext") == "mp4"]
    target = mp4_fmts or video_fmts
    target.sort(key=lambda f: f.get("height") or 0, reverse=True)
    return target[0]["url"]


async def _parse_with_ytdlp(url: str, platform: str = "unknown") -> VideoInfo:
    """使用 yt-dlp Python 模块解析任意支持平台的内容（视频/图片/其他）。"""
    info = VideoInfo(original_url=url, platform=platform)
    logger.info(f"[parser.ytdlp] called with url={url[:80]}, platform={platform}")

    # 检查是否是直接图片链接
    url_lower = url.lower()
    direct_image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
    is_direct_image = any(ext in url_lower for ext in direct_image_extensions)
    
    # 或者检查是否是 Twitter 图片（包含 /media/）
    is_twitter_media = ('pbs.twimg.com' in url_lower or 'abs.twimg.com' in url_lower)
    
    if is_direct_image or is_twitter_media:
        logger.info(f"[parser.ytdlp] 识别为直接图片链接，直接添加")
        info.images.append(url)
        info.content_type = "image"
        info.cover_url = url
        info.title = url.split('/')[-1].split('?')[0][:60]  # 提取文件名作为标题
        info.parse_method = "direct_image"
        return info

    # 准备要尝试的 URL 列表
    urls_to_try = [url]
    
    # 如果是 Twitter/X，执行完整 URL 规范化处理
    is_twitter = (platform == "twitter" or "twitter.com" in url_lower or "x.com" in url_lower or "t.co" in url_lower)
    if is_twitter:
        normalized_url = _normalize_twitter_url(url)
        urls_to_try = [normalized_url]
        # 如果规范化 URL 不同，还要加上原始 URL 作为备选
        if normalized_url != url:
            urls_to_try.append(url)
        
        # 如果 Twitter URL 有 /photo/N 后缀，尝试去掉后缀的版本
        for try_url in list(urls_to_try):
            if "/photo/" in try_url.lower():
                base_url = try_url.split("/photo/")[0]
                if base_url not in urls_to_try:
                    urls_to_try.insert(0, base_url)  # 优先试不带 /photo/N 后缀的
        logger.info(f"[parser.ytdlp] Twitter 准备尝试的 URL 列表: {urls_to_try}")

    try:
        import yt_dlp as _yt_dlp

        loop = asyncio.get_running_loop()
        # 用 cookiefile（临时文件路径）而非 cookiejar（内存对象）
        # 原因：ydl.cookiejar = jar 事后赋值的方式 yt-dlp 不会正确使用，
        # 必须在 ydl_opts 字典里通过 'cookies' 键传入文件路径才能生效。
        cookie_file_path = get_cookie_manager().get_cookie_path_for_url(url)
        if cookie_file_path:
            logger.info(f"[CookieManager] 使用 Cookie 文件: {Path(cookie_file_path).name}")
        
        # 方案 1: 基础解析选项
        ydl_opts_base = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "writethumbnail": False,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }
        # 通过 ydl_opts 的 cookiefile 字段传入 Cookie 文件路径
        if cookie_file_path:
            ydl_opts_base["cookiefile"] = cookie_file_path
        
        # 普通解析选项
        ydl_opts_video = ydl_opts_base.copy()

        data = None
        no_video_error = None
        
        # 确定解析选项（Twitter 用增强选项）
        primary_opts = ydl_opts_video
        logger.info(f"[parser.ytdlp] 使用解析选项: {'普通选项' if not is_twitter else '普通选项(Twitter Cookie注入)'}")
        
        # 将外部变量捕获传入闭包，避免引用问题
        def make_safe_extract(is_twitter_flag):
            def _safe_extract_inner(u, opts):
                """安全提取yt-dlp数据（Cookie 已通过 opts['cookiefile'] 传入）"""
                import yt_dlp
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        # 调试：检查 cookie 加载情况
                        jar_size = len(ydl.cookiejar)
                        has_auth = any(c.name == 'auth_token' for c in ydl.cookiejar)
                        logger.info(f"[parser.ytdlp] YoutubeDL cookiejar: {jar_size} cookies, auth_token={'YES' if has_auth else 'NO'}")
                        result = ydl.extract_info(u, download=False)
                        return (result, None)
                except Exception as extract_err:
                    error_str = str(extract_err).lower()
                    if is_twitter_flag and ("no video could be found" in error_str or "media #1 is not a video" in error_str):
                        logger.info(f"[parser.ytdlp] 检测到纯图片推文报错: {extract_err}")
                    return (None, extract_err)
            return _safe_extract_inner
        
        safe_extract_fn = make_safe_extract(is_twitter)
        
        for try_url in urls_to_try:
            try:
                logger.info(f"[parser.ytdlp] 尝试解析 URL: {try_url}")
                
                result, err = await loop.run_in_executor(None, safe_extract_fn, try_url, primary_opts)
                if result:
                    data = result
                    logger.info(f"[parser.ytdlp] URL {try_url} 解析成功！")
                    break
                if err:
                    error_str = str(err).lower()
                    if "no video could be found" in error_str or "media #1 is not a video" in error_str:
                        no_video_error = str(err)
                        logger.info(f"[parser.ytdlp] 检测到纯图片/无视频推文: {err}")
                    else:
                        logger.warning(f"[parser.ytdlp] URL {try_url} 解析失败: {err}")
                continue
            except Exception as outer_e:
                logger.warning(f"[parser.ytdlp] URL {try_url} 外层异常: {outer_e}")
                continue
        
        # 如果上面失败了且是 Twitter，尝试用 CLI 子进程方式（解决 Python API 的 bug）
        if not data and is_twitter:
            logger.info(f"[parser.ytdlp] Python API 失败，尝试 CLI 子进程方式")
            try:
                import subprocess, json
                # 从 venv 找 yt-dlp.exe（跨平台自动检测）
                ytdlp_exe = _find_ytdlp()
                
                for try_url in urls_to_try:
                    try:
                        # Windows 下 uvicorn 事件循环不支持 asyncio.create_subprocess_exec，
                        # 改用 run_in_executor + subprocess.run（线程池执行）
                        def _run_ytdlp(u=try_url, cp=cookie_file_path, exe=ytdlp_exe):
                            import subprocess, json
                            r = subprocess.run(
                                [exe, "--dump-json", "--no-playlist", "--skip-download", "--quiet",
                                 "--cookies", cp, u],
                                capture_output=True, timeout=30, text=True)
                            return r.stdout, r.stderr
                        
                        stdout_str, stderr_str = await loop.run_in_executor(None, _run_ytdlp)
                        # 即使 rc!=0，stdout 可能有数据（yt-dlp 在某些场景会先输出 JSON 再 crash）
                        if stdout_str.strip():
                            try:
                                cli_data = json.loads(stdout_str)
                                if cli_data and cli_data.get("formats"):
                                    data = cli_data
                                    logger.info(f"[parser.ytdlp] CLI 子进程解析成功！")
                                    break
                            except json.JSONDecodeError:
                                pass
                        if stderr_str.strip():
                            logger.warning(f"[parser.ytdlp] CLI 子进程 stderr: {stderr_str[:200]}")
                    except Exception as cli_e:
                        cli_msg = str(cli_e) or type(cli_e).__name__
                        logger.warning(f"[parser.ytdlp] CLI 子进程异常: {cli_msg}")
            except Exception as e:
                logger.warning(f"[parser.ytdlp] CLI 子进程整体异常: {e}")
        
        # 如果上面失败了且是 Twitter，强制走一次 syndication API
        if not data and is_twitter:
            logger.info(f"[parser.ytdlp] Twitter GraphQL 失败，尝试强制走 syndication API")
            try:
                ydl_opts_syndication = primary_opts.copy()
                ydl_opts_syndication['extractor_args'] = {'twitter': {'api': ['syndication']}}
                for try_url in urls_to_try:
                    try:
                        def _extract_syndication(u=try_url, opts=ydl_opts_syndication):
                            # Cookie 已通过 opts['cookies'] 传入，无需事后赋值
                            with _yt_dlp.YoutubeDL(opts) as ydl:
                                return ydl.extract_info(u, download=False)
                        data = await loop.run_in_executor(None, _extract_syndication)
                        if data:
                            logger.info(f"[parser.ytdlp] 强制 syndication API 解析成功！")
                            break
                    except Exception:
                        pass
                    if data:
                        break
            except Exception as e:
                logger.warning(f"[parser.ytdlp] 强制 syndication 也失败: {e}")
        
        if data:
            info.title = data.get("title", "") or ""
            info.desc = data.get("description", "") or ""
            info.author_name = data.get("uploader") or data.get("channel") or ""
            info.author_uid = data.get("uploader_id") or data.get("channel_id") or ""
            info.duration = int(data.get("duration") or 0)
            info.width = int(data.get("width") or 0)
            info.height = int(data.get("height") or 0)
            info.like_count = int(data.get("like_count") or 0)
            info.comment_count = int(data.get("comment_count") or 0)
            info.play_count = int(data.get("view_count") or 0)
            raw_thumb = data.get("thumbnail") or data.get("thumb") or ""
            # Bilibili yt-dlp 返回的 thumbnail URL 常缺少扩展名，自动补上 .jpg
            if raw_thumb and not raw_thumb.rsplit('.', 1)[-1].lower() in ('jpg', 'jpeg', 'png', 'webp'):
                raw_thumb += '.jpg'
            info.cover_url = raw_thumb
            info.cover_url = info.cover_url.replace('http://', 'https://') if info.cover_url else ''
            logger.info(f"[parser] yt-dlp raw cover={info.cover_url[:80] if info.cover_url else '**EMPTY**'}")
            best_url = _ytdlp_best_url(data)
            info.video_url = best_url
            info.parse_method = "ytdlp" + ("+cookie" if cookie_file_path else "")
            info.raw = {k: v for k, v in data.items() if k not in ("formats",)}
            logger.info(f"[parser] yt-dlp raw title={info.title[:30] if info.title else '**EMPTY**'}")
            logger.info(f"[parser] yt-dlp video_url={info.video_url[:80] if info.video_url else '**EMPTY**'}")
            
            # 尝试提取图片
            if not info.video_url:
                # 优先找 thumbnails 里的图片
                if 'thumbnails' in data and isinstance(data['thumbnails'], list):
                    thumbnails = [
                        t for t in data['thumbnails'] 
                        if isinstance(t, dict) and 'url' in t and t.get('url')
                    ]
                    if thumbnails:
                        # 优先选分辨率最高的
                        thumbnails.sort(
                            key=lambda x: (x.get('height') or 0, x.get('width') or 0),
                            reverse=True
                        )
                        # 添加所有有效图片（最多 10 张）
                        for t in thumbnails[:10]:
                            info.images.append(t['url'])
                        # 取最高清的作为封面
                        info.cover_url = thumbnails[0]['url']
                        info.content_type = "image"
                        logger.info(f"[parser] 提取到图片: {len(info.images)} 张")
                
                # 如果还是没图片，试试其他字段
                if not info.images and 'thumbnail' in data:
                    info.images.append(data['thumbnail'])
                    info.cover_url = data['thumbnail']
                    info.content_type = "image"
                
                logger.info(f"[parser] 最终图片数: {len(info.images)}")
            else:
                info.content_type = "video"
        else:
            info.parse_method = "ytdlp_no_data"
            logger.warning(f"[parser.ytdlp] 所有尝试的 URL 都没有获取到有效数据！")

    except asyncio.TimeoutError:
        info.parse_method = "ytdlp_timeout"
        logger.warning(f"[parser.ytdlp] TimeoutError!")
    except FileNotFoundError:
        info.parse_method = "ytdlp_not_found"
        logger.warning(f"[parser.ytdlp] FileNotFoundError!")
    except Exception as e:
        info.parse_method = f"ytdlp_exception:{e}"
        logger.warning(f"[parser.ytdlp] exception: {e}")
        import traceback
        logger.warning(f"[parser.ytdlp] Stack trace: {traceback.format_exc()}")

    logger.info(f"[parser.ytdlp] FINAL: is_valid={info.is_valid()}, content_type={info.content_type}, video_url={info.video_url[:50] if info.video_url else 'NONE'}, images={len(info.images)}")
    return info


# =============================================================================
# 主入口
# =============================================================================

async def parse(url_or_text: str) -> VideoInfo:
    """
    解析视频链接（主入口）。
    - 抖音 → iesdouyin.com 方案（无需 Cookie）
    - B站 → 官方 API（无需 Cookie）
    - 其他平台 → yt-dlp
    """
    # 超级暴力URL提取：从任意脏字符串中精准提取 https? 开头的完整链接
    import re
    url_match = re.search(r'https?://[^\s<>"\'`{}|\\^`]+', url_or_text)
    if url_match:
        url = url_match.group(0).strip()
        # 二次清理，确保末尾没有残留的特殊字符
        url = re.sub(r'[`\'",\)\]\}]+$', '', url)
    else:
        # 没有匹配到就走旧逻辑
        cleaned_input = url_or_text.strip()
        if not cleaned_input.startswith("http"):
            url = _extract_url_from_text(cleaned_input)
        else:
            url = cleaned_input
    logger.info(f"[主入口] 提取并清理后最终URL: {url[:150]}")

    platform = _detect_platform(url)
    info = VideoInfo(original_url=url, platform=platform)

    # B站使用官方 API（无需 Cookie，比 yt-dlp 更稳定）
    if platform == "bilibili":
        try:
            from app.services.video.parser_bilibili import parse_bilibili
            result = await parse_bilibili(url)
            if result.get("video_url") or result.get("images"):
                info.video_url = result.get("video_url", "")
                info.cover_url = result.get("cover_url", "")
                info.title = result.get("title", "")
                info.author_name = result.get("author_name", "")
                info.author_uid = result.get("author_uid", "")
                info.author_avatar = result.get("author_avatar", "")
                info.duration = result.get("duration", 0)
                info.width = result.get("width", 0)
                info.height = result.get("height", 0)
                info.like_count = result.get("like_count", 0)
                info.comment_count = result.get("comment_count", 0)
                info.share_count = result.get("share_count", 0)
                info.play_count = result.get("play_count", 0)
                info.content_type = result.get("content_type", "video")
                info.images = result.get("images", [])
                info.qualities = result.get("qualities", [])
                info.parse_method = result.get("parse_method", "bilibili_api")
                info.raw = result.get("raw", {})
                return info
            else:
                logger.warning("[parser] B站 API 解析失败，fallback 到 yt-dlp")
        except Exception as e:
            logger.warning(f"[parser] B站 API 解析异常，fallback 到 yt-dlp: {e}")

    # 抖音使用 iesdouyin.com 移动端方案（无需 Cookie）
    if platform == "douyin":
        try:
            from app.services.video.parser_douyin import parse_douyin
            result = await parse_douyin(url)
            if result.get("video_url") or result.get("images"):
                info.video_url = result.get("video_url", "")
                info.cover_url = result.get("cover_url", "")
                info.title = result.get("title", "")
                info.author_name = result.get("author_name", "")
                info.author_uid = result.get("author_uid", "")
                info.author_avatar = result.get("author_avatar", "")
                info.duration = result.get("duration", 0)
                info.width = result.get("width", 0)
                info.height = result.get("height", 0)
                info.like_count = result.get("like_count", 0)
                info.comment_count = result.get("comment_count", 0)
                info.share_count = result.get("share_count", 0)
                info.play_count = result.get("play_count", 0)
                info.content_type = result.get("content_type", "video")
                info.images = result.get("images", [])
                info.qualities = result.get("qualities", [])
                info.parse_method = result.get("parse_method", "iesdouyin")
                info.raw = result.get("raw", {})
                # 覆盖为 iesdouyin 分享页 URL（yt-dlp 下载必须用这个）
                info.original_url = result.get("original_url") or info.original_url
                return info
            else:
                logger.warning("[parser] iesdouyin 解析失败，fallback 到 yt-dlp")
        except Exception as e:
            logger.warning(f"[parser] iesdouyin 解析异常，fallback 到 yt-dlp: {e}")

    # 所有平台统一用 yt-dlp 兜底
    ytdlp_info = await _parse_with_ytdlp(url, platform)
    if ytdlp_info.is_valid():
        info.video_url = ytdlp_info.video_url or info.video_url
        info.title = ytdlp_info.title or info.title
        info.author_name = ytdlp_info.author_name or info.author_name
        info.cover_url = ytdlp_info.cover_url or info.cover_url
        info.duration = ytdlp_info.duration or info.duration
        info.width = ytdlp_info.width or info.width
        info.height = ytdlp_info.height or info.height
        info.images = ytdlp_info.images or info.images
        info.content_type = ytdlp_info.content_type or info.content_type
        info.parse_method = ytdlp_info.parse_method
        info.raw = ytdlp_info.raw
        return info
    
    # 如果 yt-dlp + 用户配置完整认证 Cookie 失败，用 syndication API 作为备用（不需要 Cookie）
    # 注意：无 Cookie 的 syndication API 无法获取登录可见的非公开推文，
    # 主流程必须优先用带完整 Cookie 的 yt-dlp 才能解锁全部内容！
    if platform == "twitter":
        tweet_id_match = re.search(r'status/(\d+)', url.lower())
        if tweet_id_match:
            tweet_id = tweet_id_match.group(1)
            logger.info(f"[parser] 备用方案: syndication API 解析 tweet_id={tweet_id} (无Cookie，主流程是带Cookie的yt-dlp)")
            synd_info_dict = await parse_twitter_syndication(tweet_id)
            if synd_info_dict.get("video_url") or synd_info_dict.get("images"):
                info.video_url = synd_info_dict.get("video_url", "")
                info.title = synd_info_dict.get("title", "") or info.title
                info.author_name = synd_info_dict.get("author_name", "") or info.author_name
                info.author_uid = synd_info_dict.get("author_uid", "") or info.author_uid
                info.author_avatar = synd_info_dict.get("author_avatar", "") or info.author_avatar
                info.cover_url = synd_info_dict.get("cover_url", "") or info.cover_url
                info.images = synd_info_dict.get("images", []) or info.images
                info.content_type = synd_info_dict.get("content_type", "")
                info.parse_method = synd_info_dict.get("parse_method", "")
                info.raw = synd_info_dict.get("raw")
                logger.info(f"[parser] 备用 syndication API 成功，content_type={info.content_type}")
                return info
            else:
                logger.warning(f"[parser] 备用 syndication API 也失败: {synd_info_dict.get('parse_method')}")

    return info


# =============================================================================
# 下载
# =============================================================================

async def download(info: VideoInfo, output_path: str) -> bool:
    """下载视频到指定路径"""
    if not info.is_valid():
        return False
    success = await _download_with_ytdlp(info.original_url, output_path)
    if success:
        return True
    if info.video_url and info.video_url.startswith("http"):
        return await _download_direct(info.video_url, output_path)
    return False


async def _download_with_ytdlp(url: str, output_path: str) -> bool:
    """使用 yt-dlp 下载视频"""
    try:
        loop = asyncio.get_running_loop()
        ytdlp_exe = Path(_find_ytdlp())

        cmd = [
            str(ytdlp_exe),
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "-o", output_path,
        ]

        cookie_path = get_cookie_manager().get_cookie_path_for_url(url)
        if cookie_path:
            cmd.extend(["--cookies", str(cookie_path)])

        cmd.append(url)

        # Windows 下改用 run_in_executor 避免事件循环不支持子进程
        import subprocess as _subprocess
        def _run_download():
            return _subprocess.run(
                cmd, capture_output=True, timeout=300.0, text=True)
        result = await loop.run_in_executor(None, _run_download)
        return result.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError, Exception):
        return False


async def _download_direct(url: str, output_path: str) -> bool:
    """直接 HTTP 下载（兜底）"""
    _UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _UA, "Referer": url},
            follow_redirects=True,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0),
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code == 200:
                    with open(output_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                    return True
    except Exception:
        pass
    return False


# =============================================================================
# 转为 breaker 兼容格式（向后兼容）
# =============================================================================

def to_breaker_format(info: VideoInfo) -> dict:
    """将 VideoInfo 转换为 breaker service 期望的格式"""
    return {
        "video_url": info.video_url,
        "cover_url": info.cover_url,
        "title": info.title,
        "author": {
            "name": info.author_name,
            "uid": info.author_uid,
            "avatar": info.author_avatar,
        },
        "platform": info.platform,
        "duration": info.duration,
        "width": info.width,
        "height": info.height,
        "like_count": info.like_count,
        "comment_count": info.comment_count,
        "share_count": info.share_count,
        "play_count": info.play_count,
        "content_type": info.content_type,
        "images": info.images,
        "parse_method": info.parse_method,
    }
