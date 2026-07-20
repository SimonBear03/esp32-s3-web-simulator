// SPDX-License-Identifier: GPL-2.0-only

import { FALLBACK_BOARDS } from "./boards";
import {
  embeddedElfHashes,
  inspectFirmware,
  verifyElfFirmwareMatch,
} from "./firmware";

function firmwareFile(size = 4096, header = [0xe9, 3, 0, 0]): File {
  const bytes = new Uint8Array(size);
  bytes.set(header);
  return new File([bytes], "firmware.bin", { type: "application/octet-stream" });
}

describe("inspectFirmware", () => {
  it("accepts a bounded merged ESP image", async () => {
    const result = await inspectFirmware(
      firmwareFile(),
      FALLBACK_BOARDS["cardputer-adv"],
    );

    expect(result.valid).toBe(true);
    expect(result.segmentCount).toBe(3);
    expect(result.checks[0]).toMatchObject({
      label: "Merged image header",
      value: "0xE9",
      valid: true,
    });
  });

  it("rejects bad image magic and oversize board flash", async () => {
    const board = {
      ...FALLBACK_BOARDS["cardputer-adv"],
      flash_size_bytes: 4096,
    };
    const result = await inspectFirmware(
      firmwareFile(4097, [0x7f, 3, 0, 0]),
      board,
    );

    expect(result.valid).toBe(false);
    expect(result.checks.find((check) => check.label === "Merged image header")?.valid).toBe(
      false,
    );
    expect(result.checks.find((check) => check.label === "Board flash fit")?.valid).toBe(
      false,
    );
  });

  it("matches an ELF digest embedded in an ESP-IDF application descriptor", async () => {
    const bytes = new Uint8Array(4096);
    const appOffset = 0x100;
    bytes.set([0xe9, 3, 0, 0], appOffset);
    const view = new DataView(bytes.buffer);
    const descriptorOffset = appOffset + 0x20;
    view.setUint32(descriptorOffset, 0xabcd5432, true);
    const digest = Uint8Array.from({ length: 32 }, (_value, index) => index + 1);
    bytes.set(digest, descriptorOffset + 144);
    const file = new File([bytes], "firmware.bin");
    const digestHex = [...digest]
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");

    expect(await embeddedElfHashes(file)).toEqual(new Set([digestHex]));
    expect(await verifyElfFirmwareMatch(file, digestHex)).toBe("matched");
    expect(await verifyElfFirmwareMatch(file, "f".repeat(64))).toBe("mismatched");
  });

  it("reports unavailable when legacy firmware has no ELF digest", async () => {
    expect(await verifyElfFirmwareMatch(firmwareFile(), "a".repeat(64))).toBe(
      "unavailable",
    );
  });

  it("rejects oversized input before reading it for build matching", async () => {
    const oversized = new File([new Uint8Array(8 * 1024 * 1024 + 1)], "huge.bin");

    await expect(embeddedElfHashes(oversized)).rejects.toThrow(
      "too large for browser build matching",
    );
  });
});
