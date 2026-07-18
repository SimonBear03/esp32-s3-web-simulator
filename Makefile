.PHONY: check build-qemu

check:
	./scripts/check-foundation.sh

build-qemu:
	./scripts/build-qemu.sh
