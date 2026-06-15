"""
CA 证书管理器
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("ylcraft.proxy.cert")


class CertManager:
    """CA 证书管理"""

    _CERT_DIR = Path(__file__).parent.parent.parent.parent / "data" / "certs"

    @classmethod
    def ensure_cert_dir(cls) -> Path:
        cls._CERT_DIR.mkdir(parents=True, exist_ok=True)
        return cls._CERT_DIR

    @classmethod
    def get_ca_cert_path(cls) -> str:
        return str(cls.ensure_cert_dir() / "ylcraft-ca.pem")

    @classmethod
    def get_ca_key_path(cls) -> str:
        return str(cls.ensure_cert_dir() / "ylcraft-ca-key.pem")

    @classmethod
    def ca_cert_exists(cls) -> bool:
        return os.path.exists(cls.get_ca_cert_path())

    @classmethod
    def generate_ca_cert(cls) -> str:
        """生成自签名 CA 证书"""
        path = cls.get_ca_cert_path()
        key_path = cls.get_ca_key_path()

        if cls.ca_cert_exists():
            return path

        cls.ensure_cert_dir()

        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            import datetime as dt

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "YLCraft"),
                x509.NameAttribute(NameOID.COMMON_NAME, "YLCraft Proxy CA"),
            ])

            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(dt.datetime.utcnow())
                .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, hashes.SHA256())
            )

            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ))

            with open(path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))

            logger.info(f"[CertManager] CA 证书已生成: {path}")
            return path

        except ImportError:
            logger.warning("[CertManager] cryptography 库未安装，跳过证书生成")
            # 创建占位文件
            Path(path).write_text("# CA certificate placeholder\n")
            return path
