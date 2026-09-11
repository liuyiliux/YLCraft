"""跨方言的自定义列类型。

背景：资产中枢的模型此前用 ``PGUUID(as_uuid=True)``，而 Python 注解与全项目
的取值习惯都是 ``str``（``str(uuid4())``）。二者不一致会带来两类问题：

1. PostgreSQL 方言下绑定 ``str`` 需要驱动做隐式转换，行为不确定；
2. SQLite（测试）方言下 ``Uuid`` 类型会走 ``value.hex`` 分支，绑定 ``str``
   直接抛 ``AttributeError: 'str' object has no attribute 'hex'``。
   此前测试通过「临时把全局列类型改成 String(36)」绕过，一旦在替换之前
   有别的模块触发了 mapper/语句编译缓存，缓存里就固化了旧的 ``Uuid`` 类型，
   表现为"单独跑通过、一起跑失败"的顺序敏感问题。

``GUID`` 让两端都吃 ``str``：DB 侧仍保持 PostgreSQL 原生 ``uuid`` 列（无需迁移），
SQLite 侧落 CHAR(36)，Python 侧读写统一为 ``str``，与模型注解保持一致。
"""

from __future__ import annotations

import uuid

from sqlalchemy import CHAR, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PGUUID


class GUID(TypeDecorator):
    """平台无关的 GUID：PostgreSQL 用原生 uuid，其它方言用 CHAR(36)。

    - ``process_bind_param``：``str`` / ``uuid.UUID`` 都接受（PostgreSQL 侧转成
      ``uuid.UUID`` 交给驱动，其它方言转成字符串）。
    - ``process_result_value``：统一返回 ``str``，与模型注解 ``id: str`` 一致。
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return str(value)
