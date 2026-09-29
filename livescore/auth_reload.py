"""Coalesced SIGHUP requests; one asynchronous auth-only reload at a time."""
import asyncio
from contextlib import asynccontextmanager, suppress
import signal
import threading


@asynccontextmanager
async def auth_reload_handler(auth):
    if not hasattr(signal, 'SIGHUP') or threading.current_thread() is not threading.main_thread():
        # ASGI TestClient/Windows cannot install Unix process signal handlers.
        yield
        return
    loop = asyncio.get_running_loop()
    requested = asyncio.Event()
    previous = signal.getsignal(signal.SIGHUP)
    loop.add_signal_handler(signal.SIGHUP, requested.set)

    async def worker():
        while True:
            await requested.wait()
            requested.clear()
            await auth.reload()

    task = asyncio.create_task(worker())
    try:
        yield
    finally:
        loop.remove_signal_handler(signal.SIGHUP)
        signal.signal(signal.SIGHUP, previous)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
