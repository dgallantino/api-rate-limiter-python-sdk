"""Flask before_request hook. Importing this module requires Flask."""

from __future__ import annotations

from collections.abc import Callable

from flask import Response, after_this_request, request

from api_rate_limiter.decision import BAD_BODY, DENY_BODY, evaluate, parse_fail, retry_after_seconds
from api_rate_limiter.key import KeyFn, KeyMissing, parse_key_source


def rate_limit(
    stub,
    *,
    key_fn: KeyFn | None = None,
    key: str | None = None,
    cost: int = 1,
    cost_fn: Callable[[dict[str, str]], int] | None = None,
    fail: str = "closed",
):
    """Return a function for ``app.before_request``.

    On an allow, the function schedules ``X-RateLimit-Remaining`` with
    ``after_this_request``. A deny or bad request returns a response and
    skips the view.
    """
    key_fn = key_fn or parse_key_source(key)
    fail_mode = parse_fail(fail)

    def _limit():
        headers = {name.lower(): value for name, value in request.headers.items()}
        ip = request.remote_addr or ""
        try:
            identity = key_fn(headers, ip)
        except KeyMissing:
            return _json(400, BAD_BODY)
        amount = cost_fn(headers) if cost_fn else cost
        decision = evaluate(stub, identity, amount, fail_mode)
        if decision.kind == "bad_request":
            return _json(400, BAD_BODY)
        if decision.kind == "deny":
            extra = {"X-RateLimit-Remaining": str(decision.remaining)}
            sec = retry_after_seconds(decision.retry_after_ms)
            if sec > 0:
                extra["Retry-After"] = str(sec)
            return _json(429, DENY_BODY, extra)
        if decision.kind == "allow":
            remaining = str(decision.remaining)

            @after_this_request
            def _remaining(response):
                response.headers["X-RateLimit-Remaining"] = remaining
                return response

        return None

    return _limit


def _json(status: int, body: bytes, extra: dict[str, str] | None = None) -> Response:
    response = Response(body, status=status, mimetype="application/json")
    if extra:
        response.headers.update(extra)
    return response
