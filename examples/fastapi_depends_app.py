"""FastAPI Depends example. Requires a running Check service.

Separate from fastapi_app.py: HTTP middleware on that app would check the
same request again. The route is registered after dial_aio() because the
dependency closes over the stub, and dial_aio() must run on the serving loop.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI

from api_rate_limiter import dial_aio
from api_rate_limiter.fastapi import install, rate_limit

addr = os.environ.get("CHECK_ADDR", "127.0.0.1:50051")
app = FastAPI()


def _use_sdk():
    channel, stub = dial_aio(addr)
    install(app)

    limit = rate_limit(stub, key="header:X-API-Key", cost=1, fail="closed")

    @app.get("/", dependencies=[Depends(limit)])
    async def index():
        return {"ok": True}

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
        config = uvicorn.Config(app, host="127.0.0.1", port=8001)
        await uvicorn.Server(config).serve()

    asyncio.run(_main())
