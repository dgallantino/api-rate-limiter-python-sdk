from __future__ import annotations

from types import SimpleNamespace

import grpc
import pytest
from fastapi import Depends, FastAPI
from flask import Flask
from starlette.responses import Response
from starlette.testclient import TestClient

from api_rate_limiter.decision import BAD_BODY, DENY_BODY
from api_rate_limiter.fastapi import http_middleware, install, rate_limit as fastapi_limit
from api_rate_limiter.flask import rate_limit as flask_limit


class FakeStub:
    def __init__(self, fn):
        self.fn = fn

    def Check(self, req):
        return self.fn(req)


class FakeRpcError(Exception):
    def __init__(self, code):
        self._code = code

    def code(self):
        return self._code


def _flask(stub, **kw):
    app = Flask(__name__)
    kw.setdefault("cost", 1)

    @app.get("/")
    def ok():
        return "", 204

    app.before_request(flask_limit(stub, **kw))
    return app.test_client()


def _depends(stub, **kw):
    app = FastAPI()
    install(app)
    kw.setdefault("cost", 1)

    @app.get("/", status_code=204)
    async def ok(_limit=Depends(fastapi_limit(stub, **kw))):
        return None

    return TestClient(app)


def _middleware(stub, **kw):
    app = FastAPI()
    kw.setdefault("cost", 1)

    @app.get("/")
    async def ok():
        return Response(status_code=204)

    app.middleware("http")(http_middleware(stub, **kw))
    return TestClient(app)


def _client(kind, stub, **kw):
    if kind == "flask":
        return _flask(stub, **kw)
    if kind == "depends":
        return _depends(stub, **kw)
    return _middleware(stub, **kw)


def _body(kind, rec) -> bytes:
    return rec.data if kind == "flask" else rec.content


@pytest.mark.parametrize("kind", ["flask", "depends", "middleware"])
def test_allow(kind):
    stub = FakeStub(lambda req: SimpleNamespace(allowed=True, remaining=7, retry_after_ms=0))
    rec = _client(kind, stub).get("/", headers={"X-API-Key": "free:demo"})
    assert rec.status_code == 204
    assert rec.headers["X-RateLimit-Remaining"] == "7"


@pytest.mark.parametrize("kind", ["flask", "depends", "middleware"])
def test_deny(kind):
    stub = FakeStub(lambda req: SimpleNamespace(allowed=False, remaining=0, retry_after_ms=1500))
    rec = _client(kind, stub).get("/", headers={"X-API-Key": "k"})
    assert rec.status_code == 429
    assert rec.headers["Retry-After"] == "2"
    assert rec.headers["X-RateLimit-Remaining"] == "0"
    assert _body(kind, rec) == DENY_BODY


@pytest.mark.parametrize("kind", ["flask", "depends", "middleware"])
def test_missing_key(kind):
    def boom(_req):
        raise AssertionError("check must not run")

    rec = _client(kind, FakeStub(boom)).get("/")
    assert rec.status_code == 400
    assert _body(kind, rec) == BAD_BODY


@pytest.mark.parametrize("kind", ["flask", "depends", "middleware"])
def test_fail_closed(kind):
    stub = FakeStub(lambda _req: (_ for _ in ()).throw(FakeRpcError(grpc.StatusCode.UNAVAILABLE)))
    rec = _client(kind, stub, fail="closed").get("/", headers={"X-API-Key": "k"})
    assert rec.status_code == 429
    assert rec.headers.get("Retry-After") in (None, "")
    assert _body(kind, rec) == DENY_BODY


@pytest.mark.parametrize("kind", ["flask", "depends", "middleware"])
def test_fail_open(kind):
    stub = FakeStub(lambda _req: (_ for _ in ()).throw(FakeRpcError(grpc.StatusCode.UNAVAILABLE)))
    rec = _client(kind, stub, fail="open").get("/", headers={"X-API-Key": "k"})
    assert rec.status_code == 204
    assert "X-RateLimit-Remaining" not in rec.headers


@pytest.mark.parametrize("kind", ["flask", "depends", "middleware"])
def test_invalid_argument(kind):
    stub = FakeStub(lambda _req: (_ for _ in ()).throw(FakeRpcError(grpc.StatusCode.INVALID_ARGUMENT)))
    rec = _client(kind, stub).get("/", headers={"X-API-Key": "k"})
    assert rec.status_code == 400
    assert _body(kind, rec) == BAD_BODY
