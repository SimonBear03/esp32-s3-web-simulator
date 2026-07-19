// SPDX-License-Identifier: GPL-2.0-only

import { FALLBACK_BOARDS } from "./boards";
import { inspectFirmware } from "./firmware";

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
});
