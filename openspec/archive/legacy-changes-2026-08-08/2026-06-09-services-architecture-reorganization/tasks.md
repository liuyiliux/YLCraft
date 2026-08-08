## 1. 修复 services/__init__.py

- [x] 1.1 检查当前 `services/__init__.py` 内容（确认仅含文档字符串）
- [x] 1.2 补充包级导出（如 `get_services_info` 函数或 `ServiceLocator` 类）
- [x] 1.3 验证 `from app.services import X` 不报错

## 2. 重构 breaker/__init__.py 与 service.py

- [x] 2.1 读取当前 `breaker/__init__.py` 完整内容（所有 dataclass + 函数）
- [x] 2.2 创建新的 `breaker/service.py`，将所有实现代码从 `__init__.py` 移入
- [x] 2.3 重写 `breaker/__init__.py`，仅保留文档字符串 + `from .service import *` + `__all__`
- [x] 2.4 验证 `from app.services.breaker import create_task` 仍可用
- [x] 2.5 验证 `from app.services.breaker.service import parse_video_url` 仍可用
- [x] 2.6 验证 `from app.services.breaker import AnalysisStatus` 仍可用

## 3. 规范化其余 __init__.py

- [x] 3.1 扫描 `services/` 下所有 `__init__.py`，列出仅有注释无实际导出的包
- [x] 3.2 对每个有问题的 `__init__.py`，补充实际导出或标记为待处理
- [x] 3.3 验证每个包的 `__all__` 有意义内容（不是空列表）

## 4. 明确 platforms/ 与 platform_connection/ 边界

- [x] 4.1 检查 `services/platform_connection/__init__.py`，补充职责说明文档
- [x] 4.2 检查 `services/platforms/__init__.py`，补充职责说明文档
- [x] 4.3 验证两包间无循环导入
- [x] 4.4 验证 `platform_connection/` 未导入 `platforms/` 的客户端

## 5. 验证与清理

- [x] 5.1 运行 `python -c "from app.services import *"` 验证无错误
- [x] 5.2 验证 breaker 相关 API 导入仍正常
- [x] 5.3 检查是否还有其他孤立文件或空目录待清理
