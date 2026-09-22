"""FastAPI route dependency and HTTP middleware. Importing this module requires FastAPI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import Response

from api_rate_limiter.decision import (
    BAD_BODY,
    DENY_BODY,
    evaluate_async,
    parse_fail,
    retry_after_seconds,
)
from api_rate_limiter.key import KeyFn, KeyMissing, parse_key_source


class RateLimitResponse(Exception):
    """Raised by the Depends hook so the body stays the raw deny JSON."""

    def __init__(self, response: Response):
        self.response = response


def install(app) -> None:
    """Register the handler for :class:`RateLimitResponse`. Does not wrap the app."""

    @app.exception_handler(RateLimitResponse)
    async def _rate_limit_response(_request: Request, exc: RateLimitResponse) -> Response:
        return exc.response


def rate_limit(
    stub,
    *,
    key_fn: KeyFn | None = None,
    key: str | None = None,
    cost: int = 1,
    cost_fn: Callable[[dict[str, str]], int] | None = None,
    fail: str = "closed",
):
    """Return an async dependency for ``Depends(...)``. Call :func:`install` on the app first."""
    check = _checker(stub, key_fn=key_fn, key=key, cost=cost, cost_fn=cost_fn, fail=fail)

    async def _limit(request: Request, response: Response):
        verdict = await check(request)
        if verdict.response is not None:
            raise RateLimitResponse(verdict.response)
        if verdict.remaining is not None:
            response.headers["X-RateLimit-Remaining"] = verdict.remaining

    return _limit


def http_middleware(
    stub,
    *,
    key_fn: KeyFn | None = None,
    key: str | None = None,
    cost: int = 1,
    cost_fn: Callable[[dict[str, str]], int] | None = None,
    fail: str = "closed",
):
    """Return ``(request, call_next)`` for ``@app.middleware(\"http\")``."""
    check = _checker(stub, key_fn=key_fn, key=key, cost=cost, cost_fn=cost_fn, fail=fail)

    async def _middleware(request: Request, call_next):
        verdict = await check(request)
        if verdict.response is not None:
            return verdict.response
        response = await call_next(request)
        if verdict.remaining is not None:
            response.headers["X-RateLimit-Remaining"] = verdict.remaining
        return response

    return _middleware


@dataclass
class _Verdict:
    response: Response | None = None
    remaining: str | None = None


def _checker(stub, *, key_fn, key, cost, cost_fn, fail):
    key_fn = key_fn or parse_key_source(key)
    fail_mode = parse_fail(fail)

    async def check(request: Request) -> _Verdict:
        headers = {name.lower(): value for name, value in request.headers.items()}
        ip = request.client.host if request.client else ""
        try:
            identity = key_fn(headers, ip)
        except KeyMissing:
            return _Verdict(response=_json(400, BAD_BODY))
        amount = cost_fn(headers) if cost_fn else cost
        decision = await evaluate_async(stub, identity, amount, fail_mode)
        if decision.kind == "bad_request":
            return _Verdict(response=_json(400, BAD_BODY))
        if decision.kind == "deny":
            extra = {"X-RateLimit-Remaining": str(decision.remaining)}
            sec = retry_after_seconds(decision.retry_after_ms)
            if sec > 0:
                extra["Retry-After"] = str(sec)
            return _Verdict(response=_json(429, DENY_BODY, extra))
        if decision.kind == "allow":
            return _Verdict(remaining=str(decision.remaining))
        return _Verdict()

    return check


def _json(status: int, body: bytes, extra: dict[str, str] | None = None) -> Response:
    return Response(content=body, status_code=status, media_type="application/json", headers=extra)
