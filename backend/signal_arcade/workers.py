"""Cancellation-safe ownership of synchronous work submitted to a thread."""

import asyncio
from collections.abc import Callable
from contextlib import suppress
from typing import ParamSpec, TypeVar

_Args = ParamSpec("_Args")
_Result = TypeVar("_Result")


async def await_worker(  # noqa: UP047
    worker: asyncio.Task[_Result], *, on_cancel: Callable[[], None] | None = None
) -> _Result:
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        if on_cancel is not None:
            on_cancel()
        # Cancelling the wrapper cannot stop its real thread. Repeated cancellation must
        # keep ownership until that thread exits, before locks or storage may be released.
        while not worker.done():
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(worker)
        with suppress(asyncio.CancelledError, Exception):
            worker.result()
        raise


async def joined_to_thread(  # noqa: UP047
    function: Callable[_Args, _Result], *args: _Args.args, **kwargs: _Args.kwargs
) -> _Result:
    return await await_worker(asyncio.create_task(asyncio.to_thread(function, *args, **kwargs)))
