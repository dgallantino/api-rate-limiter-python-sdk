"""Demo-only Check readiness probe.

Not part of the SDK. dial() and dial_aio() do not connect until the first
Check call. With fail="closed", a down Check service is an HTTP 429, which
looks like a rate limit. These helpers fail the example before it serves.
"""

from __future__ import annotations

import asyncio

import grpc

_TIMEOUT_S = 2


def _fail(addr: str) -> None:
    print(
        f"Check is not reachable at {addr}.\n"
        "Start it with the Compose demo in "
        "https://github.com/dgallantino/api-rate-limiter (tag v0.1.0), "
        "then run this example again.\n"
        "This probe is only for the demo. The SDK does not require it."
    )
    raise SystemExit(1)


def require_check(channel, addr: str, timeout: float = _TIMEOUT_S) -> None:
    try:
        grpc.channel_ready_future(channel).result(timeout=timeout)
    except grpc.FutureTimeoutError:
        _fail(addr)


async def require_check_aio(channel, addr: str, timeout: float = _TIMEOUT_S) -> None:
    try:
        await asyncio.wait_for(channel.channel_ready(), timeout=timeout)
    except TimeoutError:
        _fail(addr)
