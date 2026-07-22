# Voqalize public repo — root Makefile.
#
# Targets so far cover proto generation. Per-package build/test commands live
# with each package (its own Makefile or README).

PROTO_DIR        := proto
PROTO_GEN_DIR    := $(PROTO_DIR)/gen/python/voqalize/frames
PROTO_GEN_GO_DIR := $(PROTO_DIR)/gen/go/voqalize/frames
PY_SDK_WIRE_DIR  := sdk/python/src/voqalize/sdk/wire
GO_SDK_WIRE_DIR  := sdk/go/wire/framespb

.PHONY: proto proto-lint proto-breaking

## Regenerate protobuf stubs (Python + Go) and copy them into the SDK trees.
## Run after editing any *.proto under proto/.
proto:
	cd $(PROTO_DIR) && buf lint
	cd $(PROTO_DIR) && buf generate
	cp $(PROTO_GEN_DIR)/frames_pb2.py $(PY_SDK_WIRE_DIR)/_frames_pb2.py
	mkdir -p $(GO_SDK_WIRE_DIR)
	cp $(PROTO_GEN_GO_DIR)/frames.pb.go $(GO_SDK_WIRE_DIR)/frames.pb.go
	@echo "proto: regenerated and copied into sdk/python + sdk/go"

## Lint protos.
proto-lint:
	cd $(PROTO_DIR) && buf lint

## Backwards-compat check against the committed baseline.
proto-breaking:
	cd $(PROTO_DIR) && buf breaking --against '.git#branch=main'
