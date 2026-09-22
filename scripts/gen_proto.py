#!/usr/bin/env python3
"""Fetch proto/ from api-rate-limiter and generate Python gRPC stubs.

Does not vendor proto or generated code. Defaults:

  PROTO_REPO  https://github.com/dgallantino/api-rate-limiter
  PROTO_REF   v0.1.0
"""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "proto"
GEN_DIR = ROOT / "gen"
PROTO_REPO = os.environ.get("PROTO_REPO", "https://github.com/dgallantino/api-rate-limiter").rstrip("/")
PROTO_REF = os.environ.get("PROTO_REF", "v0.1.0")


def _archive_url() -> str:
    return f"{PROTO_REPO}/archive/refs/tags/{PROTO_REF}.tar.gz"


def _safe_proto_dest(parts: tuple[str, ...]) -> Path | None:
    """Map archive members .../proto/... to ROOT/proto/.... Reject escapes."""
    if "proto" not in parts:
        return None
    idx = parts.index("proto")
    rel = parts[idx:]
    if not rel or rel[0] != "proto":
        return None
    dest = ROOT.joinpath(*rel).resolve()
    try:
        dest.relative_to(PROTO_DIR.resolve())
    except ValueError:
        return None
    return dest


def fetch_proto() -> None:
    url = _archive_url()
    print(f"fetching {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "api-rate-limiter-python-sdk"})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()

    if PROTO_DIR.exists():
        shutil.rmtree(PROTO_DIR)
    PROTO_DIR.mkdir(parents=True)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as tmp:
        tmp.write(data)
        tmp.flush()
        with tarfile.open(tmp.name, "r:gz") as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                dest = _safe_proto_dest(parts)
                if dest is None:
                    continue
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(member)
                if src is None:
                    continue
                with src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)

    protos = list(PROTO_DIR.rglob("*.proto"))
    if not protos:
        raise SystemExit(f"no .proto files under {PROTO_DIR} after fetch from {url}")
    for p in sorted(protos):
        print(f"fetched {p.relative_to(ROOT)}", file=sys.stderr)


def _clean_gen() -> None:
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    for child in GEN_DIR.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _touch_init_files() -> None:
    for dirpath, _dirnames, _filenames in os.walk(GEN_DIR):
        if dirpath == str(GEN_DIR):
            continue
        init = Path(dirpath) / "__init__.py"
        if not init.exists():
            init.write_text("", encoding="utf-8")


def generate() -> None:
    try:
        from grpc_tools import protoc
    except ImportError as e:
        raise SystemExit("grpcio-tools is required: pip install -e '.[dev]'") from e

    protos = sorted(PROTO_DIR.rglob("*.proto"))
    if not protos:
        raise SystemExit(f"no .proto files under {PROTO_DIR}; run fetch first")

    _clean_gen()
    args = [
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={GEN_DIR}",
        f"--grpc_python_out={GEN_DIR}",
        *[str(p) for p in protos],
    ]
    code = protoc.main(args)
    if code != 0:
        raise SystemExit(f"protoc failed with exit {code}")
    _touch_init_files()
    for p in sorted(GEN_DIR.rglob("*.py")):
        print(f"generated {p.relative_to(ROOT)}", file=sys.stderr)


def main() -> None:
    fetch_proto()
    generate()


if __name__ == "__main__":
    main()
