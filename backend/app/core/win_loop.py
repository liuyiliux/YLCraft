"""Uvicorn loop factory that always returns a Proactor event loop on Windows.

Why this exists
---------------
Patchright launches Chromium as a **subprocess**. On Windows only
``ProactorEventLoop`` implements ``subprocess_exec``; ``SelectorEventLoop``
raises ``NotImplementedError``. Uvicorn picks the loop via
``uvicorn.loops.asyncio.asyncio_loop_factory(use_subprocess=...)``:

    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop
    return asyncio.SelectorEventLoop

``use_subprocess`` is true whenever uvicorn runs with ``--reload`` (the reloader
supervises a child process). So the common dev command
``uvicorn app.main:app --reload --port 8000`` silently switches to
``SelectorEventLoop``, and every browser-based Cookie acquisition dies with
``NotImplementedError`` — while still reporting ``success: true`` to the caller.

Wiring this factory via ``--loop app.core.win_loop:proactor_loop_factory`` keeps
``--reload`` (hot reload stays useful) **and** restores subprocess support.

Usage:
    uvicorn app.main:app --reload --port 8000 \\
        --loop app.core.win_loop:proactor_loop_factory

On non-Windows platforms this returns ``uvloop`` when available, otherwise the
default asyncio loop, so the same command works cross-platform.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Callable


def proactor_loop_factory(use_subprocess: bool = False) -> Callable[[], asyncio.AbstractEventLoop]:
    """Return a loop class that can spawn subprocesses.

    ``use_subprocess`` is accepted for signature compatibility with uvicorn's
    built-in factories, but is deliberately ignored: the whole point is to keep
    subprocess support even when uvicorn enables its reloader.
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop

    try:  # uvloop is optional
        import uvloop  # type: ignore

        return uvloop.Loop  # type: ignore[return-value]
    except ImportError:
        return asyncio.SelectorEventLoop
