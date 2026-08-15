"""Tencent Cloud COS uploader with a hand-written HMAC-SHA1 signature.

Deliberately avoids the qcloud_cos SDK: the PUT-object signature (q-sign-algorithm=sha1)
is small enough to implement directly, so YLCraft keeps no extra dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import mimetypes
import time
from pathlib import Path
from urllib.parse import quote

import httpx

logger = logging.getLogger("ylcraft.cos")


class CosStorageError(RuntimeError):
    pass


class CosStorageService:
    """Upload objects to a Tencent COS bucket and return public URLs."""

    def __init__(self, bucket: str, region: str, secret_id: str, secret_key: str, scheme: str = "https"):
        if not bucket or not secret_id or not secret_key:
            raise CosStorageError("COS 配置不完整（bucket / SecretId / SecretKey）")
        self.bucket = bucket
        self.region = region
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.scheme = scheme
        self.host = f"{bucket}.cos.{region}.myqcloud.com"

    def public_url(self, key: str) -> str:
        return f"{self.scheme}://{self.host}/{quote(key, safe='/')}"

    def _authorization(self, method: str, key: str, content_type: str, now: int) -> str:
        start = now - 60
        end = now + 3600
        key_time = f"{start};{end}"

        # Step 1: SignKey = hex(HMAC-SHA1(SecretKey, KeyTime))
        sign_key = hmac.new(
            self.secret_key.encode("utf-8"),
            key_time.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()

        # Step 2: HttpString
        uri = "/" + quote(key, safe="/")
        signed_headers = {
            "content-type": content_type,
            "host": self.host,
        }
        header_list = ";".join(sorted(signed_headers.keys()))
        header_str = "&".join(
            f"{name}={quote(str(value), safe='')}"
            for name, value in sorted(signed_headers.items())
        )
        http_string = f"{method.lower()}\n{uri}\n\n{header_str}\n"

        # Step 3: StringToSign = "sha1\nKeyTime\nSHA1(HttpString)\n"
        string_to_sign = (
            f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
        )

        # Step 4: Signature = hex(HMAC-SHA1(SignKey_as_string, StringToSign))
        signature = hmac.new(
            sign_key.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()

        return (
            f"q-sign-algorithm=sha1&q-ak={self.secret_id}"
            f"&q-sign-time={key_time}&q-key-time={key_time}"
            f"&q-header-list={header_list}&q-url-param-list="
            f"&q-signature={signature}"
        )

    async def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        url = self.public_url(key)
        auth = self._authorization("put", key, content_type, int(time.time()))
        headers = {"Authorization": auth, "Content-Type": content_type}
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True, trust_env=False) as client:
                response = await client.put(url, headers=headers, content=data)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CosStorageError(
                f"COS 上传失败 {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except Exception as exc:
            raise CosStorageError(f"COS 上传失败: {exc}") from exc
        return url

    async def upload_file(self, key: str, file_path: Path, content_type: str | None = None) -> str:
        data = file_path.read_bytes()
        if not content_type:
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        return await self.upload_bytes(key, data, content_type)


async def load_cos_service() -> CosStorageService | None:
    """Read COS config (DB first, settings.json fallback); return None when not configured."""
    try:
        from app.api.v1.settings import get_cos_config

        config = await get_cos_config()
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to load COS config: %s", exc)
        return None

    if not config.get("bucket") or not config.get("secret_id") or not config.get("secret_key"):
        return None
    return CosStorageService(
        bucket=str(config["bucket"]),
        region=str(config.get("region") or "ap-beijing"),
        secret_id=str(config["secret_id"]),
        secret_key=str(config["secret_key"]),
    )
