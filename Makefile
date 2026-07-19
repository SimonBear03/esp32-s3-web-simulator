.PHONY: check foundation lint test web-check web-e2e build-qemu base-conformance

BOARD_ID ?= cardputer-adv

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

base-conformance:
	uv run ./scripts/run-base-conformance.py \
		--qemu "$(QEMU)" \
		--rom-directory "$(ROMS)" \
		--firmware "$(FIRMWARE)" \
		--board-id "$(BOARD_ID)"
