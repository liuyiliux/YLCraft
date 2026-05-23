"""
统一 Cookie 管理器

提供跨平台 Cookie 的统一存储和读取接口：
- 数据存储：PlatformConnection 表（cookie_content Netscape 格式）+ 磁盘文件缓存
- 凭证规范：只使用 cookie_content (Netscape格式) 存储，credentials 只作为备份
- yt-dlp 集成：支持 cookie 文件路径和内存 CookieJar 两种方式

迁移说明（2026-05-21）：
- 原位于 app/services/video/parser.py 的 CookieManager
- 现统一放置于此，video/parser.py 改为兼容导入
"""

from __future__ import annotations

import json
import logging
import re
import time
from io import StringIO
from pathlib import Path
from typing import Optional

from yt_dlp.cookies import YoutubeDLCookieJar

logger = logging.getLogger("ylcraft.cookie_manager")


class CookieManager:
    """
    统一 Cookie 管理器。

    数据存储规范：
    - cookie_content (Netscape 格式) → 唯一存储位置，yt-dlp 直接使用
    - credentials (JSON) → 自动转换为 Netscape 格式

    存储架构：从 PlatformConnection 唯一存储读取 Cookie
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
                PlatformConnection, AuthType
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
                # 优先使用 conn.domains 中的域名
                domains_list = []
                if conn.domains:
                    domains_list = [d.strip().lower() for d in conn.domains.split(",") if d.strip()]
                else:
                    # 如果没有设置 domains，尝试获取该平台的默认域名
                    try:
                        plat_str = conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform)
                        from app.services.cookies.base import get_platform_domains
                        default_domains = get_platform_domains(plat_str)
                        if default_domains:
                            domains_list = [d.strip().lower() for d in default_domains.split(",") if d.strip()]
                    except Exception as e:
                        logger.debug(f"[CookieManager] 获取默认域名失败: {e}")
                
                if not domains_list:
                    # 如果还是没有域名，使用平台名进行简单匹配（回退方案）
                    plat_str = conn.platform.value if hasattr(conn.platform, 'value') else str(conn.platform)
                    if plat_str in url_domain:
                        matched.append((1, conn))
                    continue
                
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
        from urllib.parse import unquote

        cookie_content = cookie_content.strip()

        # 格式1：已经是 Netscape 格式
        if cookie_content.startswith("# Netscape HTTP Cookie File"):
            return self._clean_netscape_content(cookie_content)

        # 获取平台默认域名（从 PlatformConnection 的 domains 字段）
        default_domain = ".example.com"
        try:
            session = self._get_db_session()
            from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType
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
            pass  # 故意留空，不做 unquote
            lines.append(f"{default_domain}\t{is_dot}\t/\tFALSE\t{default_expires}\t{name}\t{value}")

        if len(lines) > 2:
            return "\n".join(lines)

        return cookie_content

    def save_cookie(self, platform: str, cookie_content: str) -> bool:
        """保存 Cookie 到 PlatformConnection 统一凭证表 + 同步写入持久 Cookie 文件"""
        from app.db.models.platform_connection import (
            PlatformConnection, PlatformType, AuthType, AcquisitionMethod, ConnectionStatus
        )

        session = self._get_db_session()
        try:
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
                from app.services.cookies.base import get_platform_domains
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
        """从 Netscape 格式提取 raw 字符串（内部方法）"""
        parts = []
        for line in cookie_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            fields = line.split('\t')
            if len(fields) >= 7:
                parts.append(f"{fields[5]}={fields[6]}")
        return "; ".join(parts)

    def extract_raw(self, cookie_content: str) -> str:
        """从 Cookie 内容提取 raw 字符串（支持多种格式）
        
        Args:
            cookie_content: Cookie 内容（Netscape格式、JSON格式或raw格式）
        
        Returns:
            raw 格式字符串 "key=value; key2=value2"
        """
        if not cookie_content:
            logger.debug("extract_raw: cookie_content is empty")
            return ""
        
        logger.debug(f"extract_raw: input starts with={cookie_content[:80]!r}, len={len(cookie_content)}")
        
        # 如果已经是 raw 格式（不包含 Netscape 标记），直接返回
        if not cookie_content.startswith("# Netscape HTTP Cookie File"):
            logger.debug("extract_raw: Not Netscape format, trying to parse")
            # 尝试解析为 Netscape 格式，然后提取 raw
            try:
                netscape = self._convert_to_netscape("generic", cookie_content)
                raw = self._netscape_to_raw(netscape)
                logger.debug(f"extract_raw: converted to raw, len={len(raw)}, preview={raw[:80]!r}")
                return raw
            except Exception as e:
                logger.debug(f"extract_raw: conversion failed: {e}, returning original")
                # 如果不是 raw 格式，直接返回原值
                return cookie_content
        # 如果是 Netscape 格式，提取 raw
        logger.debug("extract_raw: Netscape format, extracting raw")
        raw = self._netscape_to_raw(cookie_content)
        logger.debug(f"extract_raw: extracted raw, len={len(raw)}, preview={raw[:80]!r}")
        return raw

    def delete_cookie(self, platform: str) -> bool:
        """从 PlatformConnection 清空 Cookie + 删除持久文件"""
        from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType

        session = self._get_db_session()
        try:
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

    def get_cookie_file(self, platform: str) -> Optional[str]:
        """
        获取 Cookie 文件路径（Netscape 格式），如果文件不存在则从 DB 重建。

        这是供下载器使用的公共方法。
        yt-dlp 需要 cookie 文件路径，不能传内存 CookieJar。

        Returns:
            Cookie 文件路径字符串，如果 DB 中也没有则返回 None
        """
        from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType

        path = self._get_cookie_file_path(platform)

        # 文件存在，直接返回
        if path.exists():
            return str(path)

        # 文件不存在，尝试从 DB 重建
        logger.info(f"[CookieManager] Cookie 文件不存在，尝试从 DB 重建: {path}")
        session = self._get_db_session()
        try:
            try:
                plat_enum = PlatformType(platform)
            except ValueError:
                logger.warning(f"[CookieManager] 未知平台: {platform}")
                return None

            conn = session.query(PlatformConnection).filter(
                PlatformConnection.platform == plat_enum,
                PlatformConnection.auth_type == AuthType.COOKIE,
                PlatformConnection.cookie_content != None,
            ).first()

            if conn and conn.cookie_content:
                clean_content = self._clean_netscape_content(conn.cookie_content)
                path.write_text(clean_content, encoding="utf-8")
                path.chmod(0o600)
                logger.info(f"[CookieManager] 从 DB 重建 Cookie 文件成功: {path}")
                return str(path)
            else:
                logger.warning(f"[CookieManager] DB 中没有找到 {platform} 的 cookie_content")
                return None
        except Exception as e:
            logger.warning(f"[CookieManager] 从 DB 重建 Cookie 文件失败: {e}")
            return None
        finally:
            session.close()

    def list_cookies(self) -> dict[str, dict]:
        """列出所有平台 Cookie 状态（从 PlatformConnection 统一凭证表读取）"""
        from app.db.models.platform_connection import PlatformConnection, AuthType

        session = self._get_db_session()
        try:
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
        from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType

        session = self._get_db_session()
        try:
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
        from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType, ConnectionStatus

        session = self._get_db_session()
        try:
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
        from app.db.models.platform_connection import PlatformConnection, PlatformType, AuthType

        session = self._get_db_session()
        try:
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

    def validate(self, cookie_content: str) -> dict:
        """
        验证 cookie 有效性

        Returns:
            {"valid": bool, "count": int, "message": str}
        """
        if not cookie_content:
            return {"valid": False, "count": 0, "message": "Cookie 为空"}

        # 尝试解析
        parsed = self._convert_to_netscape("generic", cookie_content)
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

    def normalize_cookie(self, platform: str, cookie_content: str) -> str:
        """
        公共方法：将任意格式的 Cookie 转换为 Netscape 格式
        
        支持的输入格式：
        1. 已为 Netscape 格式（直接返回）
        2. JSON 数组格式（浏览器扩展导出）
        3. key=value; key2="value2" 字符串格式（DevTools 复制）
        
        Returns:
            Netscape 格式字符串
        """
        return self._convert_to_netscape(platform, cookie_content)

    def clean_cookie_content(self, cookie_content: str) -> str:
        """
        公共方法：清洗 Netscape Cookie 内容
        
        移除值两端的引号等，确保格式正确
        """
        return self._clean_netscape_content(cookie_content)


# =============================================================================
# 全局单例
# =============================================================================

_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    """获取 CookieManager 全局单例"""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager
