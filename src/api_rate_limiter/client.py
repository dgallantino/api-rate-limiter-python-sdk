import sys
from pathlib import Path

import grpc


def _ensure_gen_on_path() -> None:
    # Editable src layout: <root>/src/api_rate_limiter/client.py → <root>/gen
    gen = Path(__file__).resolve().parents[2] / "gen"
    if gen.is_dir():
        path = str(gen)
        if path not in sys.path:
            sys.path.insert(0, path)


_ensure_gen_on_path()

from check.v1 import check_pb2
from check.v1 import check_pb2_grpc


def dial(addr: str):
    channel = grpc.insecure_channel(addr)
    return channel, check_pb2_grpc.CheckerStub(channel)


def dial_aio(addr: str):
    channel = grpc.aio.insecure_channel(addr)
    return channel, check_pb2_grpc.CheckerStub(channel)


def make_request(key: str, cost: int):
    return check_pb2.CheckRequest(key=key, cost=cost)
