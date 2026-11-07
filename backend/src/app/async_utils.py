import asyncio


async def run_off_loop(job, /, **kwargs):
    """Run an async job on a worker thread with its own event loop.

    The jobs make many blocking Firestore calls; running them on the API's
    event loop would stall every other request until they finished.
    """
    return await asyncio.to_thread(lambda: asyncio.run(job(**kwargs)))
