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

Usage:
    uvicorn app.main:app --reload --port 8000 \\
        --loop app.core.win_loop:new_loop

On non-Windows platforms this uses ``uvloop`` when available, otherwise the
default asyncio loop, so the same command works cross-platform.
"""

import asyncio
import sys
from typing import Any


def new_loop() -> Any:
    """Build the event loop uvicorn should run on. Takes no arguments.

    Signature note (learned the hard way): when ``--loop`` points at a **custom**
    dotted path, uvicorn does *not* call it with ``use_subprocess`` — it returns
    the resolved object as-is and later calls it with **zero arguments**:

        # uvicorn/config.py, custom-path branch
        return import_from_string(self.loop)        # no (use_subprocess=...) call
        # uvicorn/_compat.py
        loop = loop_factory()                       # must yield a LOOP INSTANCE

    So this must be a plain zero-argument function returning an instance. Two
    earlier attempts failed here: returning the factory-of-a-factory (uvicorn got
    a function and crashed on ``loop.close()``), and returning
    ``asyncio.ProactorEventLoop`` directly — on Python 3.10/Windows *calling that
    class returns the class itself, not an instance*, which produced
    ``BaseProactorEventLoop.close() missing 1 required positional argument: 'self'``.
    """
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()

    try:  # uvloop is optional
        import uvloop  # type: ignore

        return uvloop.new_event_loop()
    except ImportError:
        return asyncio.new_event_loop()
