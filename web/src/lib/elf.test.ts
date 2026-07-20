// SPDX-License-Identifier: GPL-2.0-only

import { decodeBacktrace, ElfSymbolError, inspectElfSymbols, symbolicateAddress } from "./elf";

function fixtureElf(): File {
  const payload = new ArrayBuffer(0x300);
  const bytes = new Uint8Array(payload);
  const view = new DataView(payload);
  bytes.set([0x7f, 0x45, 0x4c, 0x46, 1, 1, 1]);
  view.setUint16(16, 2, true);
  view.setUint16(18, 94, true);
  view.setUint32(20, 1, true);
  view.setUint32(32, 0x200, true);
  view.setUint16(46, 40, true);
  view.setUint16(48, 4, true);

  const text = 0x200 + 40;
  view.setUint32(text + 4, 1, true);
  view.setUint32(text + 8, 0x6, true);
  view.setUint32(text + 12, 0x42000000, true);
  view.setUint32(text + 16, 0x40, true);
  view.setUint32(text + 20, 0x40, true);

  const strings = 0x200 + 80;
  view.setUint32(strings + 4, 3, true);
  view.setUint32(strings + 16, 0x80, true);
  view.setUint32(strings + 20, 12, true);
  bytes.set(new TextEncoder().encode("\0chess_loop\0"), 0x80);

  const symbols = 0x200 + 120;
  view.setUint32(symbols + 4, 2, true);
  view.setUint32(symbols + 16, 0xc0, true);
  view.setUint32(symbols + 20, 32, true);
  view.setUint32(symbols + 24, 2, true);
  view.setUint32(symbols + 36, 16, true);
  view.setUint32(0xc0 + 16, 1, true);
  view.setUint32(0xc0 + 20, 0x42000010, true);
  view.setUint32(0xc0 + 24, 0x10, true);
  view.setUint8(0xc0 + 28, 0x12);
  view.setUint16(0xc0 + 30, 1, true);

  return new File([payload], "firmware.elf", { type: "application/x-elf" });
}

describe("ELF symbol inspection", () => {
  it("extracts bounded Xtensa function symbols and resolves offsets", async () => {
    const index = await inspectElfSymbols(fixtureElf());

    expect(index.symbolCount).toBe(1);
    expect(symbolicateAddress(index, 0x42000014)).toEqual({
      address: 0x42000014,
      symbol: "chess_loop",
      offset: 4,
    });
    expect(symbolicateAddress(index, 0x42000020).symbol).toBeNull();
  });

  it("extracts, deduplicates, and bounds pasted backtrace addresses", async () => {
    const index = await inspectElfSymbols(fixtureElf());
    const decoded = decodeBacktrace(
      "Backtrace: 0x42000014:0x3fce0000 42000014 0x42000020",
      index,
    );

    expect(decoded).toEqual([
      { address: 0x42000014, symbol: "chess_loop", offset: 4 },
      { address: 0x3fce0000, symbol: null, offset: null },
      { address: 0x42000020, symbol: null, offset: null },
    ]);
  });

  it("rejects a non-Xtensa ELF instead of producing misleading symbols", async () => {
    const file = fixtureElf();
    const payload = await file.arrayBuffer();
    new DataView(payload).setUint16(18, 62, true);

    await expect(
      inspectElfSymbols(new File([payload], "wrong.elf")),
    ).rejects.toThrow(ElfSymbolError);
  });

  it("rejects a section table that escapes the bounded file", async () => {
    const payload = await fixtureElf().arrayBuffer();
    new DataView(payload).setUint32(32, payload.byteLength - 20, true);

    await expect(
      inspectElfSymbols(new File([payload], "escaped.elf")),
    ).rejects.toThrow("section table is outside");
  });

  it("rejects unbounded section counts before walking attacker data", async () => {
    const payload = await fixtureElf().arrayBuffer();
    new DataView(payload).setUint16(48, 4097, true);

    await expect(
      inspectElfSymbols(new File([payload], "unbounded.elf")),
    ).rejects.toThrow("section table is unsupported or unbounded");
  });
});
