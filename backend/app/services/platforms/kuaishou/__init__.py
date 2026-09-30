"""快手平台客户端。

⚠️ 导入 `client` 会触发 `@register_platform("kuaishou")` ——
所以这里的 import **不能删**（删了平台就不注册了）。
"""

from .client import KuaishouClient

__all__ = ["KuaishouClient"]
