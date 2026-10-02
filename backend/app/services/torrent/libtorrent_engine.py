"""libtorrent Python binding adapter.

This engine is optional. It is activated with TORRENT_ENGINE=libtorrent and
requires the libtorrent Python package to be installed in the backend venv.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from urllib.parse import unquote

import httpx

from app.services.torrent.config import TorrentConfig
from app.services.torrent.engine import TorrentEngine
from app.services.torrent.models import PUBLIC_TRACKERS, TorrentFileInfo, TorrentHealth, TorrentStatus

# ⚠️ 本模块原来**没有 logger**（2026-10-01 加 resume data 时才发现）——
# 直接写 `logger.debug(...)` 会是 NameError，且只在异常路径触发（平时测不出来）。
logger = logging.getLogger("ylcraft.torrent.libtorrent")


DHT_ROUTERS = (
    ("router.bittorrent.com", 6881),
    ("router.utorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
    ("dht.aelitis.com", 6881),
)

DHT_BOOTSTRAP_NODES = ",".join(f"{host}:{port}" for host, port in DHT_ROUTERS)

FALLBACK_LISTEN_INTERFACES = (
    "0.0.0.0:6883,[::]:6883",
    "0.0.0.0:6884,[::]:6884",
    "0.0.0.0:6885,[::]:6885",
    "0.0.0.0:6886,[::]:6886",
    "0.0.0.0:6887,[::]:6887",
    "0.0.0.0:0,[::]:0",
)

STREAM_HEAD_BYTES = 16 * 1024 * 1024
STREAM_TAIL_BYTES = 8 * 1024 * 1024
STREAM_PIECE_PRIORITY = 7


class LibtorrentEngine(TorrentEngine):
    _session = None
    _handles: dict[str, object] = {}
    _metadata_only: set[str] = set()
    _metadata_boost_at: dict[str, float] = {}
    _metadata_cache_saved: set[str] = set()
    _dht_rebind_at: float = 0.0
    _dht_rebind_index: int = 0

    def __init__(self, config: TorrentConfig):
        self.config = config
        self.lt = _import_libtorrent()
        if LibtorrentEngine._session is None:
            LibtorrentEngine._session = self._create_session()

    async def add_magnet(self, magnet: str, save_path: Path, start_paused: bool = True) -> str:
        magnet_hash = _hash_from_magnet(magnet)
        cached = self._metadata_cache_path(magnet_hash)
        if cached and cached.is_file():
            try:
                torrent_info = self.lt.torrent_info(str(cached))
                if magnet_hash not in _hashes_from_torrent_info(torrent_info):
                    raise ValueError("Cached torrent metadata hash mismatch")
                return self._add_torrent_info(torrent_info, save_path, start_paused, magnet_hash)
            except Exception:
                pass
        torrent_info = await self._fetch_remote_metadata(magnet_hash)
        if torrent_info is not None:
            return self._add_torrent_info(torrent_info, save_path, start_paused, magnet_hash)
        params = self.lt.parse_magnet_uri(magnet)
        self._ensure_magnet_trackers(params)
        self._set_param(params, "save_path", str(save_path))
        self._set_storage_mode(params)
        # ⚠️ magnet 也加载 resume data（用 magnet 里的 hash 找）
        if magnet_hash:
            self._load_resume_data_into(params, magnet_hash)
        handle = self._session.add_torrent(params)
        self._set_sequential(handle)
        torrent_hash = _hash_from_handle(handle) or _hash_from_magnet(magnet)
        if torrent_hash:
            self._handles[torrent_hash] = handle
            if start_paused:
                self._metadata_only.add(torrent_hash)
        handle.resume()
        return torrent_hash

    async def add_torrent_file(self, torrent_file: Path, save_path: Path, start_paused: bool = True) -> str:
        torrent_info = self.lt.torrent_info(str(torrent_file))
        return self._add_torrent_info(torrent_info, save_path, start_paused)

    def _add_torrent_info(self, torrent_info, save_path: Path, start_paused: bool = True, expected_hash: str = "") -> str:
        params = self._new_add_torrent_params()
        # ⚠️ 先尝试加载 resume data（有就跳过重新校验）
        try:
            ih = str(getattr(torrent_info, "info_hash", "") or "").lower()
        except Exception:
            ih = ""
        if ih:
            self._load_resume_data_into(params, ih)
        self._set_param(params, "ti", torrent_info)
        self._set_param(params, "save_path", str(save_path))
        self._set_storage_mode(params)
        handle = self._session.add_torrent(params)
        self._set_sequential(handle)
        torrent_hash = expected_hash or _hash_from_handle(handle)
        if start_paused:
            if torrent_hash:
                self._metadata_only.add(torrent_hash)
            self._apply_metadata_only(torrent_hash, handle)
        else:
            handle.resume()
        if torrent_hash:
            self._handles[torrent_hash] = handle
            self._save_metadata_cache(torrent_hash, handle)
        return torrent_hash

    async def list_torrents(self) -> list[TorrentStatus]:
        # ⚠️ 先处理 alert（把 `save_resume_data` 的结果写盘）——
        # 这个接口会被前端**定期轮询**，正好当"心跳"用。
        self._drain_alerts()
        items: list[TorrentStatus] = []
        for torrent_hash, handle in list(self._handles.items()):
            if not handle.is_valid():
                continue
            status = handle.status()
            has_metadata = handle.has_metadata()
            if not has_metadata:
                self._boost_metadata_discovery(torrent_hash, handle)
            else:
                self._save_metadata_cache(torrent_hash, handle)
            self._apply_metadata_only(torrent_hash, handle)
            items.append(
                TorrentStatus(
                    torrent_hash=torrent_hash,
                    name=status.name or _torrent_name(handle),
                    state=_state_name(self.lt, status),
                    progress=float(getattr(status, "progress", 0) or 0),
                    download_speed=int(getattr(status, "download_rate", 0) or 0),
                    upload_speed=int(getattr(status, "upload_rate", 0) or 0),
                    downloaded_bytes=int(getattr(status, "total_done", 0) or 0),
                    total_size=int(getattr(status, "total_wanted", 0) or 0),
                    save_path=str(self.config.download_dir),
                    error=_metadata_hint(status, handle, self._session, self.config) if not has_metadata else _status_error(status),
                )
            )
        return items

    async def list_files(self, torrent_hash: str) -> list[TorrentFileInfo]:
        handle = self._get_handle(torrent_hash)
        if not handle or not handle.is_valid() or not handle.has_metadata():
            return []
        self._save_metadata_cache(torrent_hash, handle)
        self._apply_metadata_only(torrent_hash, handle)
        torrent_info = handle.get_torrent_info()
        files = torrent_info.files()
        progress_bytes = self._file_progress(handle)
        result: list[TorrentFileInfo] = []
        for index in range(files.num_files()):
            size = int(files.file_size(index) or 0)
            done = int(progress_bytes[index] or 0) if index < len(progress_bytes) else 0
            result.append(
                TorrentFileInfo(
                    index=index,
                    name=files.file_path(index),
                    size=size,
                    progress=(done / size) if size else 0.0,
                    priority=int(handle.file_priority(index)),
                )
            )
        return result

    async def select_files(self, torrent_hash: str, file_indexes: list[int]) -> None:
        handle = self._require_handle(torrent_hash)
        if not handle.has_metadata():
            raise RuntimeError("Torrent metadata is not ready yet")
        selected = {int(i) for i in file_indexes}
        torrent_info = handle.get_torrent_info()
        for index in range(torrent_info.files().num_files()):
            handle.file_priority(index, 1 if index in selected else 0)
        self._set_sequential(handle)
        self._metadata_only.discard((torrent_hash or "").lower())

    async def prioritize_streaming(self, torrent_hash: str, file_index: int) -> None:
        handle = self._require_handle(torrent_hash)
        if not handle.has_metadata():
            raise RuntimeError("Torrent metadata is not ready yet")
        target_index = int(file_index)
        torrent_info = handle.get_torrent_info()
        files = torrent_info.files()
        if target_index < 0 or target_index >= files.num_files():
            raise ValueError("Torrent file not found")
        try:
            handle.file_priority(target_index, STREAM_PIECE_PRIORITY)
        except Exception:
            pass
        self._prioritize_file_edges(handle, torrent_info, target_index)
        self._set_sequential(handle)
        self._metadata_only.discard((torrent_hash or "").lower())
        await self.resume(torrent_hash)

    async def get_health(self, torrent_hash: str) -> TorrentHealth | None:
        handle = self._get_handle(torrent_hash)
        if not handle or not handle.is_valid():
            return TorrentHealth(
                torrent_hash=(torrent_hash or "").lower(),
                reason="任务尚未加载到本地 libtorrent 会话，可能需要刷新任务或重启后重新载入。",
            )
        status = handle.status()
        has_metadata = handle.has_metadata()
        if not has_metadata:
            self._boost_metadata_discovery(torrent_hash, handle)
        return _health_from_libtorrent_status(
            self.lt,
            torrent_hash,
            status,
            handle,
            self._session,
            self.config,
            has_metadata,
        )

    async def pause(self, torrent_hash: str) -> None:
        handle = self._require_handle(torrent_hash)
        # ⚠️ 暂停前**请求保存 resume data**（2026-10-01）
        # 这样下次启动能跳过"重新校验全部已下载数据"。
        # 实际写盘在 `_drain_alerts`（前端轮询 list_torrents 时触发）。
        self._save_resume_data(torrent_hash, handle)
        handle.pause()

    async def close(self) -> None:
        """关闭引擎 —— **先保存所有 resume data**（2026-10-01 加）。

        ⚠️ 原来是直接 `return None`，什么都不做 —— 于是进程退出时
        **所有种子的校验进度都丢了**，下次启动要重新校验全部数据。

        这里：请求保存 → 等一会儿让 libtorrent 生成 → 处理 alert 写盘。

        ⚠️ 注意 `_session` 是**类变量**（单例），这里**不销毁**它 ——
        否则下次请求会拿不到 handle。
        """
        try:
            session = self._session
            if session is None:
                return
            # 1) 请求保存所有种子的 resume data
            for th, handle in list(self._handles.items()):
                try:
                    if handle.is_valid():
                        handle.save_resume_data()
                except Exception:
                    continue
            # 2) 等一会儿让它生成（异步的，不等就丢了）
            await asyncio.sleep(1.5)
            # 3) 处理 alert 写盘
            self._drain_alerts()
        except Exception:
            pass
        return None

    async def resume(self, torrent_hash: str) -> None:
        handle = self._require_handle(torrent_hash)
        handle.resume()
        self._ensure_handle_trackers(handle)
        try:
            handle.force_reannounce(0)
        except Exception:
            pass
        try:
            handle.force_dht_announce()
        except Exception:
            pass

    async def refresh_metadata(self, torrent_hash: str) -> None:
        handle = self._require_handle(torrent_hash)
        self._start_dht(self._session)
        self._maybe_rebind_stalled_dht()
        self._ensure_handle_trackers(handle)
        try:
            handle.resume()
        except Exception:
            pass
        try:
            handle.force_reannounce(0)
        except Exception:
            try:
                handle.force_reannounce()
            except Exception:
                pass
        try:
            handle.force_dht_announce()
        except Exception:
            pass

    async def boost_trackers(self, torrent_hash: str) -> None:
        await self.refresh_metadata(torrent_hash)

    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        handle = self._handles.pop(torrent_hash.lower(), None)
        self._metadata_only.discard(torrent_hash.lower())
        self._metadata_boost_at.pop(torrent_hash.lower(), None)
        if not handle:
            return
        option = self._delete_option(delete_files)
        self._session.remove_torrent(handle, option)

    def _create_session(self):
        settings = {
            "listen_interfaces": self.config.listen_interfaces,
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "announce_to_all_trackers": True,
            "announce_to_all_tiers": True,
            "dht_bootstrap_nodes": DHT_BOOTSTRAP_NODES,
            "enable_outgoing_utp": True,
            "enable_incoming_utp": True,
            "connections_limit": 200,
        }
        try:
            session = self.lt.session(settings)
        except TypeError:
            session = self.lt.session()
            try:
                session.apply_settings(settings)
            except Exception:
                pass
        self._start_dht(session)
        return session

    def _start_dht(self, session) -> None:
        for host, port in DHT_ROUTERS:
            try:
                session.add_dht_router(host, port)
            except Exception:
                pass
        try:
            if not session.is_dht_running():
                session.start_dht()
        except Exception:
            pass

    def _ensure_magnet_trackers(self, params) -> None:
        trackers = list(getattr(params, "trackers", None) or [])
        if trackers:
            return
        self._set_param(params, "trackers", list(PUBLIC_TRACKERS))
        self._set_param(params, "tracker_tiers", [0 for _ in PUBLIC_TRACKERS])

    def _ensure_handle_trackers(self, handle) -> None:
        try:
            existing = {
                str(item.get("url") or "").strip()
                for item in handle.trackers()
                if str(item.get("url") or "").strip()
            }
        except Exception:
            existing = set()
        for tracker in PUBLIC_TRACKERS:
            if tracker in existing:
                continue
            try:
                handle.add_tracker({"url": tracker, "tier": 0})
            except Exception:
                pass

    def _metadata_cache_path(self, torrent_hash: str) -> Path | None:
        normalized = (torrent_hash or "").strip().lower()
        if not normalized:
            return None
        return self.config.download_dir / "_metadata_cache" / f"{normalized}.torrent"

    async def _fetch_remote_metadata(self, torrent_hash: str):
        if not torrent_hash or not self.config.metadata_cache_urls:
            return None
        urls = [_metadata_cache_url(template, torrent_hash) for template in self.config.metadata_cache_urls]
        urls = [url for url in urls if url]
        if not urls:
            return None
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.config.metadata_cache_timeout,
        ) as client:
            tasks = [asyncio.create_task(self._download_metadata_bytes(client, url)) for url in urls]
            try:
                for task in asyncio.as_completed(tasks):
                    data = await task
                    if not data:
                        continue
                    torrent_info = self._try_cache_metadata_bytes(torrent_hash, data)
                    if torrent_info is not None:
                        for pending in tasks:
                            if not pending.done():
                                pending.cancel()
                        return torrent_info
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        return None

    async def _download_metadata_bytes(self, client: httpx.AsyncClient, url: str) -> bytes:
        try:
            response = await client.get(url)
            if response.status_code >= 400:
                return b""
            data = response.content
            if self.config.metadata_cache_max_bytes and len(data) > self.config.metadata_cache_max_bytes:
                return b""
            return data
        except Exception:
            return b""

    def _try_cache_metadata_bytes(self, torrent_hash: str, data: bytes):
        if not data:
            return None
        path = self._metadata_cache_path(torrent_hash)
        if path is None:
            return None
        tmp_path = path.with_suffix(".torrent.remote.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_bytes(data)
            torrent_info = self.lt.torrent_info(str(tmp_path))
            if torrent_hash not in _hashes_from_torrent_info(torrent_info):
                return None
            tmp_path.replace(path)
            self._metadata_cache_saved.add(torrent_hash)
            return torrent_info
        except Exception:
            return None
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def _save_metadata_cache(self, torrent_hash: str, handle) -> None:
        key = (torrent_hash or "").strip().lower()
        if not key or key in self._metadata_cache_saved:
            return
        if not handle or not handle.is_valid() or not handle.has_metadata():
            return
        path = self._metadata_cache_path(key)
        if path is None:
            return
        if path.is_file():
            self._metadata_cache_saved.add(key)
            return
        try:
            torrent_info = handle.get_torrent_info()
            generated = self.lt.create_torrent(torrent_info).generate()
            data = self.lt.bencode(generated)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".torrent.tmp")
            tmp_path.write_bytes(data)
            tmp_path.replace(path)
            self._metadata_cache_saved.add(key)
        except Exception:
            pass

    def _boost_metadata_discovery(self, torrent_hash: str, handle) -> None:
        key = (torrent_hash or "").lower()
        now = time.monotonic()
        if now - self._metadata_boost_at.get(key, 0) < 30:
            return
        self._metadata_boost_at[key] = now
        self._start_dht(self._session)
        self._maybe_rebind_stalled_dht()
        self._ensure_handle_trackers(handle)
        try:
            handle.resume()
        except Exception:
            pass
        try:
            handle.force_reannounce(0)
        except Exception:
            try:
                handle.force_reannounce()
            except Exception:
                pass
        try:
            handle.force_dht_announce()
        except Exception:
            pass

    def _maybe_rebind_stalled_dht(self) -> None:
        if self._session_dht_nodes(self._session) > 0:
            return
        now = time.monotonic()
        if now - LibtorrentEngine._dht_rebind_at < 60:
            return
        listen_interfaces = FALLBACK_LISTEN_INTERFACES[
            LibtorrentEngine._dht_rebind_index % len(FALLBACK_LISTEN_INTERFACES)
        ]
        LibtorrentEngine._dht_rebind_index += 1
        LibtorrentEngine._dht_rebind_at = now
        try:
            self._session.apply_settings({
                "listen_interfaces": listen_interfaces,
                "dht_bootstrap_nodes": DHT_BOOTSTRAP_NODES,
            })
        except Exception:
            pass
        try:
            self._session.reopen_network_sockets()
        except Exception:
            pass
        self._start_dht(self._session)

    @staticmethod
    def _session_dht_nodes(session) -> int:
        try:
            return int(getattr(session.status(), "dht_nodes", 0) or 0)
        except Exception:
            return 0

    def _new_add_torrent_params(self):
        factory = getattr(self.lt, "add_torrent_params", None)
        return factory() if factory else {}

    # =========================================================================
    # Resume data（断点续传 —— 2026-10-01 加）
    # =========================================================================
    #
    # ## 为什么需要
    #
    # libtorrent 本身**会**对已下载分片做校验续传：重新 add 同一种子，
    # 它会扫描现有文件、校验分片、只下缺的部分。
    #
    # **但**没有 resume data 时必须**重新校验全部已下载数据**
    # （几十 GB 的种子要扫很久，表现为"重启后卡在 checking"）。
    # resume data 保存了"哪些分片已确认"的位图，加载后**跳过校验**。
    #
    # ## 存哪
    #
    # `<下载目录>/_resume_data/<hash>.resume`（与 `_metadata_cache` 同级）

    def _resume_data_path(self, torrent_hash: str) -> Path | None:
        normalized = (torrent_hash or "").strip().lower()
        if not normalized:
            return None
        return self.config.download_dir / "_resume_data" / f"{normalized}.resume"

    def _load_resume_data_into(self, params, torrent_hash: str) -> bool:
        """把 `.resume` 的内容合并进 `params`（成功返回 True）。

        ⚠️ 失败**不能中断添加** —— resume data 只是优化，
        没有它 libtorrent 退回"重新校验"，功能仍正常。

        ## ⚠️ 两个坑（2026-10-01 实测，都踩了）

        ### 坑 1：`getattr(...) or rd.get(...)` 是错的

        `read_resume_data()` 返回 `libtorrent.add_torrent_params`
        **对象**（不是 dict），**没有 `.get` 方法**。
        当 `getattr` 返回 `None` 时（如 magnet 还没元数据，`ti` 就是 None），
        会去调 `rd.get(key)` → `AttributeError` → 被 except 吞掉
        → 整个加载返回 False。症状：resume 文件明明写出来了，加载**永远失败**。

        ### 坑 2：不能 `setattr(params, "resume_data", bytes)`

        实测报 **C++ 签名不匹配**：

            None.None(add_torrent_params, bytes)
            did not match C++ signature: ...

        libtorrent 2.0 的 `resume_data` 不是裸 bytes 字段。
        **正确做法**：`read_resume_data()` 返回的就是一个
        `add_torrent_params` —— 直接把它上面的字段搬到我们的 params 即可。
        """
        path = self._resume_data_path(torrent_hash)
        if not path or not path.is_file():
            return False
        try:
            data = path.read_bytes()
            load = getattr(self.lt, "read_resume_data", None)
            if load is None:
                return False
            rd = load(data)
            # 新版 API 返回 (params, error) 元组；旧版直接返回 params
            if isinstance(rd, tuple):
                rd = rd[0]
            if rd is None:
                return False

            # ⚠️ 逐字段搬运（**不要** setattr resume_data=bytes，见坑 2）
            moved = 0
            for key in (
                "ti", "info_hash", "info_hashes", "trackers",
                "tracker_tiers", "url_seeds", "save_path",
                "storage_mode", "flags", "file_priorities",
                "max_connections", "upload_limit", "download_limit",
            ):
                try:
                    val = getattr(rd, key, None)
                except Exception:
                    continue
                if val is None or val == [] or val == "":
                    continue
                try:
                    self._set_param(params, key, val)
                    moved += 1
                except Exception:
                    # 单个字段不接受就跳过（不同版本字段名/类型有差异）
                    continue
            return moved > 0
        except Exception as exc:
            logger.debug("[torrent] 读取 resume data 失败 %s: %s", path.name, exc)
            return False

    def _save_resume_data(self, torrent_hash: str, handle) -> None:
        """**请求**保存 resume data（异步）。

        ⚠️ 这只是请求 —— libtorrent 在后台生成，完成后发
        `save_resume_data_alert`。真正的写盘在 `_drain_alerts()` 里。
        不处理 alert 的话 resume data **永远写不出去**（常见坑）。
        """
        if not handle or not handle.is_valid():
            return
        try:
            handle.save_resume_data()
        except Exception:
            pass

    def _drain_alerts(self) -> None:
        """处理 libtorrent 异步 alert（主要是 resume data 写盘）。"""
        session = self._session
        if session is None:
            return
        pop = getattr(session, "pop_alerts", None)
        if pop is None:
            return
        try:
            alerts = pop()
        except Exception:
            return

        for alert in alerts or []:
            try:
                name = type(alert).__name__
                if "save_resume_data" not in name:
                    continue
                h = getattr(alert, "handle", None)
                th = _hash_from_handle(h) if h is not None else ""
                if not th:
                    continue
                params = getattr(alert, "params", None)
                if params is None:
                    continue
                write = getattr(self.lt, "write_resume_data_buf", None)
                if write is None:
                    write = getattr(self.lt, "write_resume_data", None)
                if write is None:
                    continue
                data = write(params)
                if isinstance(data, tuple):
                    data = data[0]
                path = self._resume_data_path(th)
                if not path or not data:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".resume.tmp")
                tmp.write_bytes(data)
                tmp.replace(path)      # 原子替换
            except Exception:
                continue

    def _set_param(self, params, key: str, value) -> None:
        if isinstance(params, dict):
            params[key] = value
        else:
            setattr(params, key, value)

    def _set_storage_mode(self, params) -> None:
        storage_mode = _storage_mode_sparse(self.lt)
        if storage_mode is not None:
            self._set_param(params, "storage_mode", storage_mode)

    def _set_sequential(self, handle) -> None:
        setter = getattr(handle, "set_sequential_download", None)
        if setter:
            setter(True)

    def _file_progress(self, handle) -> list[int]:
        try:
            return list(handle.file_progress())
        except Exception:
            return []

    def _prioritize_file_edges(self, handle, torrent_info, file_index: int) -> None:
        try:
            files = torrent_info.files()
            file_size = int(files.file_size(file_index) or 0)
        except Exception:
            return
        if file_size <= 0:
            return
        windows = [
            (0, min(STREAM_HEAD_BYTES, file_size)),
            (max(file_size - STREAM_TAIL_BYTES, 0), min(STREAM_TAIL_BYTES, file_size)),
        ]
        pieces: set[int] = set()
        for offset, length in windows:
            pieces.update(_mapped_pieces(torrent_info, file_index, offset, length))
        for piece in sorted(pieces):
            try:
                handle.piece_priority(piece, STREAM_PIECE_PRIORITY)
            except Exception:
                pass

    def _delete_option(self, delete_files: bool) -> int:
        if not delete_files:
            return 0
        for owner_name in ("remove_flags_t", "options_t"):
            owner = getattr(self.lt, owner_name, None)
            value = getattr(owner, "delete_files", None) if owner else None
            if value is not None:
                return value
        return 1

    def _apply_metadata_only(self, torrent_hash: str, handle) -> None:
        key = (torrent_hash or "").lower()
        if key not in self._metadata_only or not handle.has_metadata():
            return
        try:
            torrent_info = handle.get_torrent_info()
            for index in range(torrent_info.files().num_files()):
                handle.file_priority(index, 0)
            handle.pause()
        finally:
            self._metadata_only.discard(key)

    def _get_handle(self, torrent_hash: str):
        return self._handles.get((torrent_hash or "").lower())

    def _require_handle(self, torrent_hash: str):
        handle = self._get_handle(torrent_hash)
        if not handle or not handle.is_valid():
            raise RuntimeError("Torrent is not loaded in libtorrent session")
        return handle


def _import_libtorrent():
    try:
        import libtorrent as lt  # type: ignore

        return lt
    except ImportError as exc:
        raise RuntimeError("TORRENT_ENGINE=libtorrent requires installing the libtorrent Python package") from exc


def _storage_mode_sparse(lt):
    owner = getattr(lt, "storage_mode_t", None)
    value = getattr(owner, "storage_mode_sparse", None) if owner else None
    if value is not None:
        return value
    return getattr(lt, "storage_mode_sparse", None)


def _hash_from_magnet(magnet: str) -> str:
    marker = "btih:"
    if marker not in magnet.lower():
        return ""
    start = magnet.lower().index(marker) + len(marker)
    return unquote(magnet[start:].split("&", 1)[0]).lower()


def _hash_from_handle(handle) -> str:
    try:
        hashes = handle.info_hashes()
        value = getattr(hashes, "v1", None) or getattr(hashes, "v2", None)
        if value:
            return str(value).lower()
    except Exception:
        pass
    try:
        return str(handle.info_hash()).lower()
    except Exception:
        return ""


def _hashes_from_torrent_info(torrent_info) -> set[str]:
    values: set[str] = set()
    try:
        value = str(torrent_info.info_hash()).lower()
        if value:
            values.add(value)
    except Exception:
        pass
    try:
        hashes = torrent_info.info_hashes()
        for name in ("v1", "v2"):
            value = getattr(hashes, name, None)
            if value:
                values.add(str(value).lower())
    except Exception:
        pass
    return values


def _metadata_cache_url(template: str, torrent_hash: str) -> str:
    value = (template or "").strip()
    if not value:
        return ""
    upper_hash = torrent_hash.upper()
    lower_hash = torrent_hash.lower()
    if "{" in value:
        try:
            return value.format(hash=upper_hash, hash_lower=lower_hash, hash_upper=upper_hash)
        except Exception:
            return ""
    return value.replace("%HASH%", upper_hash).replace("%hash%", lower_hash)


def _torrent_name(handle) -> str:
    try:
        if handle.has_metadata():
            return handle.get_torrent_info().name()
    except Exception:
        return ""
    return ""


def _state_name(lt, status) -> str:
    state = getattr(status, "state", None)
    if getattr(status, "paused", False):
        return "paused"
    state_t = getattr(lt, "torrent_status", None)
    if state_t:
        if state == getattr(state_t, "downloading_metadata", object()):
            return "metadl"
        if state == getattr(state_t, "downloading", object()):
            return "downloading"
        if state == getattr(state_t, "finished", object()) or state == getattr(state_t, "seeding", object()):
            return "uploading"
        if state == getattr(state_t, "checking_files", object()):
            return "checkingdl"
    return "downloading"


def _mapped_pieces(torrent_info, file_index: int, offset: int, length: int) -> set[int]:
    if length <= 0:
        return set()
    try:
        request = torrent_info.map_file(file_index, int(offset), int(length))
        piece_length = int(torrent_info.piece_length() or 0)
        piece_count = int(torrent_info.num_pieces() or 0)
        first_piece = int(getattr(request, "piece", 0) or 0)
        start_in_piece = int(getattr(request, "start", 0) or 0)
        request_length = int(getattr(request, "length", length) or length)
    except Exception:
        return set()
    if piece_length <= 0 or piece_count <= 0:
        return {first_piece}
    last_piece = first_piece + max(0, (start_in_piece + request_length - 1) // piece_length)
    last_piece = min(last_piece, piece_count - 1)
    return set(range(max(first_piece, 0), last_piece + 1))


def _health_from_libtorrent_status(
    lt,
    torrent_hash: str,
    status,
    handle,
    session,
    config: TorrentConfig,
    has_metadata: bool,
) -> TorrentHealth:
    trackers, tracker_failures = _tracker_stats(handle)
    dht_nodes, has_incoming, is_listening, listen_port = _session_stats(session)
    state = _state_name(lt, status)
    health = TorrentHealth(
        torrent_hash=(torrent_hash or "").lower(),
        state=state,
        normalized_status=TorrentStatus(torrent_hash=torrent_hash, state=state).normalized_status,
        has_metadata=has_metadata,
        progress=float(getattr(status, "progress", 0) or 0),
        download_speed=int(getattr(status, "download_rate", 0) or 0),
        upload_speed=int(getattr(status, "upload_rate", 0) or 0),
        peers=int(getattr(status, "num_peers", 0) or 0),
        seeds=int(getattr(status, "num_seeds", 0) or 0),
        connections=int(getattr(status, "num_connections", 0) or 0),
        dht_nodes=dht_nodes,
        tracker_count=trackers,
        tracker_failures=tracker_failures,
        is_listening=is_listening,
        listen_port=listen_port,
        has_incoming_connections=has_incoming,
    )
    if not has_metadata:
        health.reason = _metadata_hint(status, handle, session, config)
    return health


def _status_error(status) -> str:
    error = getattr(status, "error", None)
    if not error:
        return ""
    text = str(error)
    return "" if text in {"Success", "success"} else text


def _session_stats(session) -> tuple[int, bool, bool, int]:
    dht_nodes = 0
    has_incoming = False
    is_listening = False
    listen_port = 0
    if session is None:
        return dht_nodes, has_incoming, is_listening, listen_port
    try:
        session_status = session.status()
        dht_nodes = int(getattr(session_status, "dht_nodes", 0) or 0)
        has_incoming = bool(getattr(session_status, "has_incoming_connections", False))
    except Exception:
        pass
    try:
        is_listening = bool(session.is_listening())
    except Exception:
        pass
    try:
        listen_port = int(session.listen_port() or 0)
    except Exception:
        pass
    return dht_nodes, has_incoming, is_listening, listen_port


def _tracker_stats(handle) -> tuple[int, int]:
    trackers = 0
    tracker_failures = 0
    try:
        tracker_items = list(handle.trackers())
        trackers = len(tracker_items)
        for item in tracker_items:
            if int(item.get("fails") or 0) > 0:
                tracker_failures += 1
    except Exception:
        pass
    return trackers, tracker_failures


def _metadata_hint(status, handle, session=None, config: TorrentConfig | None = None) -> str:
    peers = int(getattr(status, "num_peers", 0) or 0)
    seeds = int(getattr(status, "num_seeds", 0) or 0)
    connections = int(getattr(status, "num_connections", 0) or 0)
    dht_nodes, has_incoming, is_listening, listen_port = _session_stats(session)
    trackers, tracker_failures = _tracker_stats(handle)
    cache_sources = len(config.metadata_cache_urls) if config else 0
    if dht_nodes <= 0:
        state_hint = "DHT 暂未连上节点，通常是本机网络、防火墙或当前端口的 UDP 不通。"
    elif connections > 0:
        state_hint = "已经连到 Peer，但暂时没有 Peer 返回 metadata，可能是该 hash 只有云盘缓存。"
    else:
        state_hint = "正在通过 DHT 和 Tracker 寻找可提供 metadata 的 Peer。"
    return (
        "正在获取种子元数据："
        f"缓存源={cache_sources}，DHT节点={dht_nodes}，Peer={peers}，连接={connections}，"
        f"Tracker={trackers}，Tracker失败={tracker_failures}，"
        f"监听={is_listening}，端口={listen_port}，入站={has_incoming}。"
        f"{state_hint} 可以点击“重试元数据”重新公告。"
    )
