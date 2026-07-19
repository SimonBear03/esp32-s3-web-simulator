# syntax=docker/dockerfile:1.10
# SPDX-License-Identifier: GPL-2.0-only

ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${BUILD_IMAGE} AS build

ARG QEMU_COMMIT=40edccac415693c5130f91c01d84176ae6008566

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        libgcrypt20-dev \
        libglib2.0-dev \
        libpixman-1-dev \
        libseccomp-dev \
        ninja-build \
        pkg-config \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git init qemu \
    && git -C qemu remote add origin https://github.com/espressif/qemu.git \
    && git -C qemu fetch --depth=1 origin "${QEMU_COMMIT}" \
    && git -C qemu checkout --detach FETCH_HEAD \
    && test "$(git -C qemu rev-parse HEAD)" = "${QEMU_COMMIT}"

COPY emulator/qemu/patches/ /src/patches/
RUN for patch_file in /src/patches/*.patch; do \
        git -C /src/qemu apply --check "${patch_file}"; \
        git -C /src/qemu apply "${patch_file}"; \
    done

WORKDIR /src/qemu
RUN ./configure \
        --target-list=xtensa-softmmu \
        --disable-curses \
        --disable-docs \
        --disable-gtk \
        --disable-opengl \
        --disable-sdl \
        --disable-slirp \
        --disable-virglrenderer \
        --disable-vnc \
        --disable-werror \
        --enable-seccomp \
    && ninja -C build qemu-system-xtensa \
    && build/qemu-system-xtensa -sandbox help >/dev/null

FROM ${RUNTIME_IMAGE} AS runtime

ARG QEMU_COMMIT=40edccac415693c5130f91c01d84176ae6008566

LABEL org.opencontainers.image.title="ESP32-S3 simulator worker" \
      org.opencontainers.image.source="https://github.com/SimonBear03/esp32-s3-web-simulator" \
      org.opencontainers.image.licenses="GPL-2.0-only" \
      com.zillionvisionary.esp32-simulator.qemu-commit="${QEMU_COMMIT}"

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        libgcrypt20 \
        libglib2.0-0 \
        libpixman-1-0 \
        libseccomp2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /src/qemu/build/qemu-system-xtensa \
    /opt/esp32-s3/bin/qemu-system-xtensa
COPY --from=esp32rom /esp32s3_rev0_rom.bin \
    /opt/esp32-s3/share/qemu/esp32s3_rev0_rom.bin

RUN chmod 0555 /opt/esp32-s3/bin/qemu-system-xtensa \
    && chmod 0444 /opt/esp32-s3/share/qemu/esp32s3_rev0_rom.bin \
    && /opt/esp32-s3/bin/qemu-system-xtensa -sandbox help >/dev/null

WORKDIR /runtime
ENV LANG=C.UTF-8 PATH=/opt/esp32-s3/bin:/usr/bin:/bin

