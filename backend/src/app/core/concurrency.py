"""
Keeping blocking work off the event loop.

The API is async: every route handler and dependency is a coroutine, and
one event loop serves every request. A blocking call made on that loop (the
Firestore SDK, Firebase Auth, the Resend client) stalls every other request
until it returns, so those calls go through one of these helpers instead.

    run_blocking(fn, *args)   a blocking function, on a worker thread
    run_off_loop(job, **kw)   an async job that itself makes blocking calls
                              (the Firestore-backed citation jobs), on a
                              worker thread with its own event loop

Code written against Postgres uses the async session (app.core.db) and
needs neither. tests/test_async_backend.py checks all of this.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


async def run_blocking(fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> T:
    """Run a blocking function on a worker thread and await its result."""
    return await asyncio.to_thread(fn, *args, **kwargs)


async def run_off_loop(job: Callable[..., Awaitable[T]], /, **kwargs) -> T:
    """Run an async job on a worker thread with its own event loop.

    The citation and publication jobs make many blocking Firestore calls;
    running them on the API's event loop would stall every other request
    until they finished.
    """
    return await asyncio.to_thread(lambda: asyncio.run(job(**kwargs)))

