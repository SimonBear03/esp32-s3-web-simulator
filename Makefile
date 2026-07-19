.PHONY: check foundation lint test web-check web-e2e build-qemu build-worker-image base-conformance sandbox-probe

BOARD_ID ?= cardputer-adv
WORKER_SANDBOX ?= direct
BWRAP ?= /usr/bin/bwrap

check: foundation lint test web-check

foundation:
	./scripts/check-foundation.sh

lint:
	uv run ruff check .

test:
	uv run pytest

web-check:
	npm --prefix web run check

web-e2e:
	npm --prefix web run test:e2e

build-qemu:
	./scripts/build-qemu.sh

build-worker-image:
	./scripts/build-worker-image.sh

base-conformance:
	uv run ./scripts/run-base-conformance.py \
		--qemu "$(QEMU)" \
		--rom-directory "$(ROMS)" \
		--firmware "$(FIRMWARE)" \
		--board-id "$(BOARD_ID)" \
		--sandbox "$(WORKER_SANDBOX)" \
		--sandbox-executable "$(BWRAP)"

sandbox-probe:
	uv run ./scripts/probe-worker-sandbox.py --sandbox-executable "$(BWRAP)"
