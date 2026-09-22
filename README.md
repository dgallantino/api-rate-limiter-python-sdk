# api-rate-limiter Python SDK

Python Pattern B client for [api-rate-limiter](https://github.com/dgallantino/api-rate-limiter): wrap a Starlette/FastAPI (ASGI) or Flask (WSGI) app so each request is checked against the Check gRPC service before origin work runs.

This repo does **not** ship the API definition or generated stubs. `make proto` pulls [`proto/`](https://github.com/dgallantino/api-rate-limiter/tree/v0.1.0/proto) from tag **v0.1.0** of the service repo and writes Python gRPC stubs into `gen/` (both directories are gitignored).

## Requirements

- Python 3.11+
- A running Check service ([Compose demo](https://github.com/dgallantino/api-rate-limiter#5-minute-live-demo-compose) listens on `:50051`)

## Develop

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make proto
make test
```

`make proto` must run before the client can import `check.v1`. Without Make: `python scripts/gen_proto.py` then `pytest`.

`PROTO_REF` (default `v0.1.0`) and `PROTO_REPO` can be overridden in the environment.

## Usage

Denied requests return HTTP 429 and do not hit origin work. Identity defaults to the `X-API-Key` header (`key="header:X-API-Key"` or `key="ip"`). Adapter `fail` is independent of Redis fail mode on Check: `closed` (default) denies when Check is down; `open` lets the request through.

### ASGI (Starlette / FastAPI)

```python
from fastapi import FastAPI
from api_rate_limiter import RateLimitMiddleware, dial_aio

channel, stub = dial_aio("127.0.0.1:50051")
app = FastAPI()
app.add_middleware(
    RateLimitMiddleware,
    stub=stub,
    key="header:X-API-Key",
    cost=1,
    fail="closed",
)
```

### WSGI (Flask)

```python
from flask import Flask
from api_rate_limiter import RateLimitWSGI, dial

app = Flask(__name__)
channel, stub = dial("127.0.0.1:50051")
app.wsgi_app = RateLimitWSGI(
    app.wsgi_app,
    stub,
    key="header:X-API-Key",
    cost=1,
    fail="closed",
)
```

### Deny contract

- **429** `{"error":"too_many_requests"}`
- `X-RateLimit-Remaining`
- `Retry-After` in seconds (`ceil(retry_after_ms / 1000)`), omitted when that is 0
- Missing key or Check `InvalidArgument` → **400** `{"error":"bad_request"}`
- Allowed responses get `X-RateLimit-Remaining`, then the origin handler runs

## Running Check

Start the service with the parent Compose demo (`docker compose up --build` in [api-rate-limiter](https://github.com/dgallantino/api-rate-limiter)). This SDK only talks to Check over gRPC; it does not run Redis or the proxy.

## Examples

[`examples/flask_app.py`](examples/flask_app.py) and [`examples/fastapi_app.py`](examples/fastapi_app.py) are runnable copies of the usage above. Install the dev extra, generate stubs, and start Check first.

```bash
pip install -e ".[dev]"
make proto
python examples/flask_app.py
python examples/fastapi_app.py
```

Flask listens on `127.0.0.1:5000`. FastAPI listens on `127.0.0.1:8000`. `CHECK_ADDR` overrides the Check address (default `127.0.0.1:50051`).

```bash
curl -H 'X-API-Key: demo' http://127.0.0.1:5000/
curl -H 'X-API-Key: demo' http://127.0.0.1:8000/
```

Each example waits for Check before it serves. That probe is only for the demo. The SDK does not require it; without it, a down Check service is a normal fail-closed HTTP 429.
