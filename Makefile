.PHONY: check foundation lint test build-qemu

check: foundation lint test

foundation:
	./scripts/check-foundation.sh

lint:
	uv run ruff check .

test:
	uv run pytest

build-qemu:
	./scripts/build-qemu.sh
