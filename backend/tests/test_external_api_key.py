from __future__ import annotations

from app.core.external_api_auth import hash_external_key
from app.db.models.external_api_key import ExternalApiKey


def test_hash_external_key_deterministic():
    assert hash_external_key("abc") == hash_external_key("abc")
    assert hash_external_key("abc") != hash_external_key("abd")
    assert len(hash_external_key("abc")) == 64


def test_external_api_key_defaults():
    k = ExternalApiKey(name="外部 Agent", key_hash="h", key_prefix="ylk_ab")
    assert k.scope == "read"
    assert k.rate_limit_per_min == 60
    assert k.active is True
