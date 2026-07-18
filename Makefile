.PHONY: check foundation lint test build-qemu base-conformance

check: foundation lint test

foundation:
	./scripts/check-foundation.sh

lint:
	uv run ruff check .

test:
	uv run pytest

build-qemu:
	./scripts/build-qemu.sh

base-conformance:
	uv run ./scripts/run-base-conformance.py \
		--qemu "$(QEMU)" \
		--rom-directory "$(ROMS)" \
		--firmware "$(FIRMWARE)"
