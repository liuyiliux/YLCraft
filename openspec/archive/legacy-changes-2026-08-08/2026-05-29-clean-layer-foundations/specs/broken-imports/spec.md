## ADDED Requirements

### Requirement: 不存在模块的导入必须移除或修正
所有 Python 源文件中引用的模块和符号 MUST 在代码库中实际存在。任何 `from X import Y` 中的 X SHALL 对应一个可导入的 Python 模块，Y SHALL 是该模块中真实存在的符号。

#### Scenario: 引用不存在的模块
- **WHEN** 扫描发现 `from app.services.backend_registry import BackendManager`
- **THEN** 该导入 MUST 被替换为正确的等价调用（`from app.services.ai import get_ai_service`），因为 `app.services.backend_registry` 模块在代码库中不存在

#### Scenario: 验证脚本
- **WHEN** 运行 `python -c "import <module>"` 检查所有 import 语句
- **THEN** 每个 import 语句 MUST 能成功执行，不抛出 `ModuleNotFoundError` 或 `ImportError`
