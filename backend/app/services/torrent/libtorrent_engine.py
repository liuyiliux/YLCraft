"""libtorrent Python binding adapter.

This engine is optional. It is activated with TORRENT_ENGINE=libtorrent and
requires the libtorrent Python package to be installed in the backend venv.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from app.services.torrent.config import TorrentConfig
from app.services.torrent.engine import TorrentEngine
from app.services.torrent.models import TorrentFileInfo, TorrentStatus


class LibtorrentEngine(TorrentEngine):
    _session = None
    _handles: dict[str, object] = {}

    def __init__(self, config: TorrentConfig):
        self.config = config
        self.lt = _import_libtorrent()
        if LibtorrentEngine._session is None:
            LibtorrentEngine._session = self._create_session()

    async def add_magnet(self, magnet: str, save_path: Path, start_paused: bool = True) -> str:
        params = self.lt.parse_magnet_uri(magnet)
        self._set_param(params, "save_path", str(save_path))
        self._set_storage_mode(params)
        handle = self._session.add_torrent(params)
        self._set_sequential(handle)
        if start_paused:
            handle.pause()
        else:
            handle.resume()
        torrent_hash = _hash_from_handle(handle) or _hash_from_magnet(magnet)
        if torrent_hash:
            self._handles[torrent_hash] = handle
        return torrent_hash

    async def add_torrent_file(self, torrent_file: Path, save_path: Path, start_paused: bool = True) -> str:
        torrent_info = self.lt.torrent_info(str(torrent_file))
        params = self._new_add_torrent_params()
        self._set_param(params, "ti", torrent_info)
        self._set_param(params, "save_path", str(save_path))
        self._set_storage_mode(params)
        handle = self._session.add_torrent(params)
        self._set_sequential(handle)
        if start_paused:
            handle.pause()
        else:
            handle.resume()
        torrent_hash = _hash_from_handle(handle)
        if torrent_hash:
            self._handles[torrent_hash] = handle
        return torrent_hash

    async def list_torrents(self) -> list[TorrentStatus]:
        items: list[TorrentStatus] = []
        for torrent_hash, handle in list(self._handles.items()):
            if not handle.is_valid():
                continue
            status = handle.status()
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
                )
            )
        return items

    async def list_files(self, torrent_hash: str) -> list[TorrentFileInfo]:
        handle = self._get_handle(torrent_hash)
        if not handle or not handle.is_valid() or not handle.has_metadata():
            return []
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

    async def pause(self, torrent_hash: str) -> None:
        self._require_handle(torrent_hash).pause()

    async def resume(self, torrent_hash: str) -> None:
        self._require_handle(torrent_hash).resume()

    async def delete(self, torrent_hash: str, delete_files: bool = False) -> None:
        handle = self._handles.pop(torrent_hash.lower(), None)
        if not handle:
            return
        option = self._delete_option(delete_files)
        self._session.remove_torrent(handle, option)

    async def close(self) -> None:
        return None

    def _create_session(self):
        settings = {
            "listen_interfaces": "0.0.0.0:6881",
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
        }
        try:
            return self.lt.session(settings)
        except TypeError:
            session = self.lt.session()
            try:
                session.apply_settings(settings)
            except Exception:
                pass
            return session

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
