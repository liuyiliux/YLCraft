# Design: 去重 B站共享常量与方法

## 存放位置

`backend/app/services/platforms/bilibili/utils.py`

该文件已是 B站共享基础设施（现有 `extract_account_info_from_cookie()` 等）。

## 搬移内容

从两个文件中提取以下 6 项到 utils.py：

| 符号 | 原有位置 | 内容 |
|------|---------|------|
| `BILI_QUALITY_MAP` | download only | `{127: "8K", 80: "1080P", 64: "720P", …}` |
| `BILI_RESOLUTION_MAP` | download (公共) / parser (私有 `_` 前缀) | `{80: "1920x1080", 64: "1280x720", …}` |
| `_QUALITY_BITRATE_MAP` | 两边各一份 | `{80: 6_000_000, 64: 3_000_000, …}` |
| `_quality_to_resolution()` | 两边各一份 | qn → 分辨率字符串 |
| `_get_filesize_for_qn()` | 两边各一份 | durl size 优先，否则码率估算 |
| `_normalize_resolution()` | download only | `"1080p"` → `"1920x1080"` |

## Import 变更

两处改为：

```python
from app.services.platforms.bilibili.utils import (
    BILI_QUALITY_MAP,
    BILI_RESOLUTION_MAP,
    _quality_to_resolution,
    _get_filesize_for_qn,
    _normalize_resolution,
)
```

`_QUALITY_BITRATE_MAP` 已内嵌在 `_get_filesize_for_qn` 中使用，无需显式 import。

## parser_bilibili.py 中的适配

parser 侧原使用 `_BILI_RESOLUTION_MAP`（私有前缀），需要全局替换为 `BILI_RESOLUTION_MAP`。该符号在 parser 中仅在 `_quality_to_resolution()` 内部引用，而该函数本身也已搬走，故 parser 侧无额外适配。
