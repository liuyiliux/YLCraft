"""AcquisitionMethod 枚举完整性回归测试。

真机故障（2026-09-25）：Cookie 获取流程走到最后一步保存连接时，
日志报 `[PatchrightManager] _save_to_db failed: PATCHRIGHT`。

**真实原因不是数据库枚举，而是 Python 枚举根本没有 PATCHRIGHT 成员** ——
`AcquisitionMethod` 只定义了 MANUAL / PLAYWRIGHT / QRCODE，而代码写的是
`AcquisitionMethod.PATCHRIGHT`，抛的是 `AttributeError`。

误导来自日志写法 `logger.error(f"... failed: {e}")`：只打 `str(e)`，
**丢掉了异常类型**，日志里只剩 `PATCHRIGHT`，看着像数据库枚举报错。
（与 `PlatformType.FANQIE` 那次是同一类事故：Python 枚举改了，PG 原生枚举没跟上。）
"""

from __future__ import annotations

import inspect
import re

import pytest


def test_patchright_member_exists():
    """代码在用的 AcquisitionMethod.PATCHRIGHT 必须真实存在。

    缺失时 AttributeError 会被 except 吞掉，表现为"保存连接失败"，
    但日志只剩一个词，极难定位。
    """
    from app.db.models.platform_connection import AcquisitionMethod

    assert hasattr(AcquisitionMethod, "PATCHRIGHT"), (
        "AcquisitionMethod 缺少 PATCHRIGHT 成员；"
        "patchright_manager._save_to_db 会因此 AttributeError"
    )
    assert AcquisitionMethod.PATCHRIGHT.value == "patchright"


def test_playwright_member_kept_for_legacy_rows():
    """保留 PLAYWRIGHT：历史连接可能仍存这个值，删了会读不出来。"""
    from app.db.models.platform_connection import AcquisitionMethod

    assert hasattr(AcquisitionMethod, "PLAYWRIGHT")


def test_model_accepts_patchright_acquisition_method():
    """用真实模型构造，确认能落 ORM（而非仅枚举可访问）。"""
    from app.db.models.platform_connection import (
        AcquisitionMethod,
        AuthType,
        ConnectionStatus,
        PlatformConnection,
        PlatformType,
    )

    conn = PlatformConnection(
        id="probe",
        platform=PlatformType.FANQIE,
        name="probe",
        auth_type=AuthType.COOKIE,
        status=ConnectionStatus.ACTIVE,
        acquisition_method=AcquisitionMethod.PATCHRIGHT,
    )
    assert conn.acquisition_method is AcquisitionMethod.PATCHRIGHT


def test_save_to_db_log_includes_exception_type():
    """异常日志必须带类型。

    只打 str(e) 是这次误判的直接原因：AttributeError 被记成了
    一个看起来像枚举值的裸词 PATCHRIGHT。
    """
    from app.services.cookies import patchright_manager as pm

    source = inspect.getsource(pm)
    # 不得出现 "failed: {e}" 这类丢类型的写法
    assert not re.search(r"""failed:\s*\{e\}""", source), (
        "日志不得只打 str(e)，必须包含 type(e).__name__ 以便定位"
    )
    assert "type(e).__name__" in source


@pytest.mark.asyncio
async def test_pg_enum_contains_patchright_if_postgres():
    """PG 原生枚举需含大写 PATCHRIGHT（SQLAlchemy 存 name/大写）。

    非 Postgres（如 SQLite 测试库）无此类型，跳过。
    """
    from sqlalchemy import text

    from app.db.database import get_async_session

    async with get_async_session() as session:
        try:
            rows = await session.execute(
                text(
                    "SELECT enumlabel FROM pg_enum "
                    "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                    "WHERE pg_type.typname = 'acquisitionmethod'"
                )
            )
            values = {r[0] for r in rows}
        except Exception:
            pytest.skip("not a PostgreSQL database")

    assert "PATCHRIGHT" in values, (
        f"PG acquisitionmethod 缺 PATCHRIGHT（需 ALTER TYPE）；现有：{sorted(values)}"
    )
