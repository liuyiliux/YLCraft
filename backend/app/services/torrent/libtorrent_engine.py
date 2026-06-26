"""libtorrent Python binding adapter.

This engine is optional. It is activated with TORRENT_ENGINE=libtorrent and
requires the libtorrent Python package to be installed in the backend venv.
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import unquote

from app.services.torrent.config import TorrentConfig
from app.services.torrent.engine import TorrentEngine
from app.services.torrent.models import TorrentFileInfo, TorrentStatus


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

DEFAULT_TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://tracker.moeking.me:6969/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker-udp.gbitt.info:80/announce",
)


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
        params = self.lt.parse_magnet_uri(magnet)
        self._ensure_magnet_trackers(params)
        self._set_param(params, "save_path", str(save_path))
        self._set_storage_mode(params)
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
                    error=_metadata_hint(status, handle, self._session) if not has_metadata else _status_error(status),
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

    async def pause(self, torrent_hash: str) -> None:
        self._require_handle(torrent_hash).pause()

    async def resume(self, torrent_hash: str) -> None:
        self._require_handle(torrent_hash).resume()

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

    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        handle = self._handles.pop(torrent_hash.lower(), None)
        self._metadata_only.discard(torrent_hash.lower())
        self._metadata_boost_at.pop(torrent_hash.lower(), None)
        if not handle:
            return
        option = self._delete_option(delete_files)
        self._session.remove_torrent(handle, option)

    async def close(self) -> None:
        return None

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
        self._set_param(params, "trackers", list(DEFAULT_TRACKERS))
        self._set_param(params, "tracker_tiers", [0 for _ in DEFAULT_TRACKERS])

    def _ensure_handle_trackers(self, handle) -> None:
        try:
            existing = {
                str(item.get("url") or "").strip()
                for item in handle.trackers()
                if str(item.get("url") or "").strip()
            }
        except Exception:
            existing = set()
        for tracker in DEFAULT_TRACKERS:
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


def _status_error(status) -> str:
    error = getattr(status, "error", None)
    if not error:
        return ""
    text = str(error)
    return "" if text in {"Success", "success"} else text


def _metadata_hint(status, handle, session=None) -> str:
    peers = int(getattr(status, "num_peers", 0) or 0)
    seeds = int(getattr(status, "num_seeds", 0) or 0)
    connections = int(getattr(status, "num_connections", 0) or 0)
    dht_nodes = 0
    has_incoming = False
    is_listening = False
    listen_port = 0
    if session is not None:
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
    trackers = 0
    tracker_errors: list[str] = []
    try:
        tracker_items = list(handle.trackers())
        trackers = len(tracker_items)
        for item in tracker_items:
            message = str(item.get("message") or item.get("last_error") or "").strip()
            if message and message not in {"Success", "success"}:
                tracker_errors.append(message)
    except Exception:
        pass
    tracker_suffix = f" tracker_error={tracker_errors[0]}" if tracker_errors else ""
    return (
        "等待种子元数据："
        f"peers={peers}, seeds={seeds}, connections={connections}, "
        f"trackers={trackers}, dht_nodes={dht_nodes}, incoming={has_incoming}, "
        f"listening={is_listening}, port={listen_port}{tracker_suffix}。"
        "如果长时间取不到，通常是该 magnet 没有可提供 metadata 的活跃节点，"
        "或本机网络/防火墙阻止 DHT/UDP；可以点击“重试元数据”重新公告。"
    )
