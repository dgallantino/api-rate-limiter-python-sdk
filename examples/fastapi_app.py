"""FastAPI example. Requires a running Check service.

dial_aio() binds the channel to the running event loop, so the SDK setup
runs inside the loop that serves the app, and the demo probe runs after it.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from api_rate_limiter import RateLimitMiddleware, dial_aio

addr = os.environ.get("CHECK_ADDR", "127.0.0.1:50051")
app = FastAPI()


@app.get("/")
async def index():
    return {"ok": True}


def _use_sdk():
    channel, stub = dial_aio(addr)
    app.add_middleware(
        RateLimitMiddleware,
        stub=stub,
        key="header:X-API-Key",
        cost=1,
        fail="closed",
    )
    return channel


if __name__ == "__main__":
    import asyncio

    import uvicorn

    from check_ready import require_check_aio

    async def _main() -> None:
        channel = _use_sdk()
        # Demo only. Not required to use this SDK. dial_aio() does not connect
        # until the first request; without this check, a down Check service
        # looks like HTTP 429.
        await require_check_aio(channel, addr)
        config = uvicorn.Config(app, host="127.0.0.1", port=8000)
        await uvicorn.Server(config).serve()

    asyncio.run(_main())
