"""Flask example. Requires a running Check service."""

from __future__ import annotations

import os

from flask import Flask, jsonify

from api_rate_limiter import RateLimitWSGI, dial

addr = os.environ.get("CHECK_ADDR", "127.0.0.1:50051")
channel, stub = dial(addr)
app = Flask(__name__)


@app.get("/")
def index():
    return jsonify(ok=True)


app.wsgi_app = RateLimitWSGI(
    app.wsgi_app,
    stub,
    key="header:X-API-Key",
    cost=1,
    fail="closed",
)

if __name__ == "__main__":
    # Demo only. Not required to use this SDK. dial() does not connect
    # until the first request; without this check, a down Check service
    # looks like HTTP 429.
    from check_ready import require_check

    require_check(channel, addr)
    app.run(host="127.0.0.1", port=5000)
