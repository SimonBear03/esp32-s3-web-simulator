# Initial Architecture

## Product Contract

The simulator accepts the same merged ESP32-S3 firmware image or ELF intended
for physical hardware and executes it without replacing the firmware's runtime
or application APIs.

The web interface should provide a virtual device shell, framebuffer, controls,
serial console, debugger, power controls, and deterministic event recording.

## Runtime Boundary

The initial deployment direction is server-side emulation:

```text
Browser client
  device UI, input, serial, debugger
             |
        documented WebSocket/API protocol
             |
Simulation session service
  validation, isolation, quotas, recording
             |
One emulator worker per active session
  ESP32-S3 execution and board device models
```

The browser protocol should remain engine-neutral so a future open-source
client-side WebAssembly engine can implement the same contract.

## Initial Device Models

### Cardputer ADV

- ESP32-S3FN8 with 8 MB flash and no PSRAM
- ST7789-compatible 240 x 135 display path
- TCA8418 keyboard controller and key events
- NVS-backed preferences and simulated reset/power cycles
- serial output, FreeRTOS behavior, and debugger integration

### StickS3

- ESP32-S3-PICO-1-N8R8 with 8 MB flash and 8 MB PSRAM
- ST7789-compatible 135 x 240 display path
- physical button inputs
- logical power/battery states and NVS
- virtual BMI270 input after the base device is conformant

## Application Compatibility Milestones

Cardputer Chess is the first compatibility and stress application. The
simulator should boot its unmodified merged firmware, display the real UI,
accept keyboard controls, preserve preferences across restarts, and support
playing a complete game. Because that application is in progress, it does not
replace the simulator-owned conformance firmware as the release gate.

The existing StickS3 companion is the second acceptance application for display,
buttons, NVS, overlays, and graceful behavior when BLE is unavailable.

## Debugging Contract

The product should eventually expose:

- UART console and panic/backtrace decoding
- pause, resume, reset, and deterministic replay
- breakpoints plus CPU register and memory inspection
- GDB integration where supported by the emulator
- SPI, I2C, GPIO, timing, and power-event traces
- downloadable session diagnostics that exclude uploaded firmware by default

## Power Fidelity

The initial model is behavioral, not an electrical circuit simulator. It should
represent USB attachment, battery voltage/percentage, charging, backlight,
sleep/deep sleep, wake sources, reset, and injected brownouts. Accurate current
consumption and thermal estimates require later calibration against physical
devices.

## Licensing Boundary

QEMU and QEMU-derived device models must retain their required copyleft terms.
The web client and orchestration service should communicate with emulator
workers over a documented process/network protocol rather than assume that all
components can be relicensed as one work.

Do not bundle Espressif ROM binaries until their redistribution terms have been
verified. Do not copy official M5Stack product artwork; create original device
visuals and identify profiles as compatible devices without implying
endorsement.
