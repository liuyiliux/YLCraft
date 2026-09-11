"""回归防护：except 块绑定的异常变量不得在块外被引用。

背景
----
Python 3 在 except 块**结束时**会删除 `as e` 绑定的变量。若因缩进错误把「写失败日志」
或 `raise HTTPException(... {e})` 落到 except 块之外，这些语句引用 `e` 会抛
`UnboundLocalError`，从而**掩盖真实异常**。

实例（`app/api/v1/characters.py` 的角色立绘生图）：provider 连接失败后，
错误处理路径自身抛 `UnboundLocalError`，日志里只剩
`log write failed: local variable 'e' referenced before assignment` 与 500，
真正的 `OpenAI API error: Connection error.` 被吞掉。

本测试用 **AST** 扫描后端源码（按函数作用域），确保该模式不再出现；
并自带一段自检，防止检测逻辑本身失效后变成"永远通过"的空测试。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_APP = Path(__file__).resolve().parents[1] / 'app'
EXCLUDE_PARTS = ('__pycache__',)


def _iter_py_files():
    for path in sorted(BACKEND_APP.rglob('*.py')):
        if any(part in EXCLUDE_PARTS for part in path.parts):
            continue
        yield path


def _handler_spans(scope):
    """返回作用域内所有绑定了异常变量的 except 块：(变量名, 起始行, 结束行)。"""
    spans = []
    for node in ast.walk(scope):
        if not isinstance(node, ast.ExceptHandler) or not node.name:
            continue
        end = max(
            (getattr(stmt, 'end_lineno', None) or stmt.lineno) for stmt in node.body
        )
        spans.append((node.name, node.lineno, end))
    return spans


def _find_out_of_scope_uses(tree, label):
    issues = []
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        spans = _handler_spans(scope)
        if not spans:
            continue
        for name, _start, end in spans:
            for node in ast.walk(scope):
                if not isinstance(node, ast.Name) or node.id != name:
                    continue
                if not isinstance(node.ctx, ast.Load):
                    continue
                line = node.lineno
                if line <= end:
                    continue  # 仍在 except 块内，属于正常用法
                # 被另一个同样绑定该名字的 except 块覆盖 → 正常（e 被重新绑定）
                if any(n == name and s <= line <= e for n, s, e in spans):
                    continue
                issues.append((label, line, name))
    return sorted(set(issues))


def test_no_exception_var_used_outside_its_except_block():
    offenders = []
    for path in _iter_py_files():
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        except SyntaxError as exc:  # 语法问题应由其它检查负责，不在此重复断言
            pytest.fail(f'{path} 无法解析: {exc}')
        offenders.extend(
            _find_out_of_scope_uses(tree, str(path.relative_to(BACKEND_APP.parent)))
        )

    assert not offenders, (
        '发现 except 块之外仍引用其异常变量（会抛 UnboundLocalError 并掩盖真实异常）：\n'
        + '\n'.join(f'  {file}:L{line}  变量 `{var}`' for file, line, var in offenders)
        + '\n修法：把写日志的 try 与 raise 缩进到 except 块内部。'
    )


def test_detector_actually_catches_the_bug():
    """自检：确认检测逻辑真的能发现该模式，避免测试变成摆设。"""

    # 错误写法：日志与 raise 缩进回到与 try/except 同级，已跳出 except 块
    bad = ast.parse(
        '\n'.join(
            [
                'async def f():',
                '    try:',
                '        await g()',
                '    except Exception as e:',
                '        logger.exception(e)',
                '    try:',
                '        await write_log(str(e))',
                '    except Exception as log_err:',
                '        pass',
                '    raise HTTPException(status_code=500, detail=f"failed: {e}")',
            ]
        )
    )
    assert _find_out_of_scope_uses(bad, 'bad.py'), '检测器未能发现该错误模式，测试已失效'

    # 正确写法：日志与 raise 都留在 except 块内
    good = ast.parse(
        '\n'.join(
            [
                'async def f():',
                '    try:',
                '        await g()',
                '    except Exception as e:',
                '        logger.exception(e)',
                '        try:',
                '            await write_log(str(e))',
                '        except Exception as log_err:',
                '            pass',
                '        raise HTTPException(status_code=500, detail=f"failed: {e}")',
            ]
        )
    )
    assert not _find_out_of_scope_uses(good, 'good.py'), '正确写法被误报'
