# Voqalize public repo — root Makefile.
#
# Targets so far cover proto generation. Per-package build/test commands live
# with each package (its own Makefile or README).

PROTO_DIR        := proto
PROTO_GEN_DIR    := $(PROTO_DIR)/gen/python/voqalize/frames
PY_SDK_WIRE_DIR  := sdk/python/src/voqalize/sdk/wire

.PHONY: proto proto-lint

## Regenerate protobuf stubs (Python) and copy them into the SDK tree.
## Run after editing any *.proto under proto/.
proto:
	cd $(PROTO_DIR) && buf lint
	cd $(PROTO_DIR) && buf generate
	cp $(PROTO_GEN_DIR)/frames_pb2.py $(PY_SDK_WIRE_DIR)/_frames_pb2.py
	@echo "proto: regenerated and copied into sdk/python"

## Lint protos.
proto-lint:
	cd $(PROTO_DIR) && buf lint

