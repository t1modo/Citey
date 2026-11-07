"""
Keeping blocking work off the event loop.

The API is async: every route handler and dependency is a coroutine, and
one event loop serves every request. A blocking call made on that loop
(Firebase Auth, the Resend client) stalls every other request until it
returns, so those calls go through run_blocking instead, which runs them on
a worker thread.

Code written against Postgres uses the async session (app.core.db) and
does not need it. tests/test_async_backend.py checks all of this.
"""

import asyncio
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


async def run_blocking(fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> T:
    """Run a blocking function on a worker thread and await its result."""
    return await asyncio.to_thread(fn, *args, **kwargs)

