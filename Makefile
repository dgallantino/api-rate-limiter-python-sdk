PYTHON ?= python3
export PROTO_REF ?= v0.1.0
export PROTO_REPO ?= https://github.com/dgallantino/api-rate-limiter

.PHONY: proto test

proto:
	$(PYTHON) scripts/gen_proto.py

test: proto
	$(PYTHON) -m pytest
