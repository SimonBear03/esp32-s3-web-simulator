// SPDX-License-Identifier: GPL-2.0-only

import { FramebufferPacketError, parseFramebufferPacket } from "./framebuffer";

function packet(width: number, height: number, pixels: number[]): ArrayBuffer {
  const buffer = new ArrayBuffer(14 + pixels.length);
  const bytes = new Uint8Array(buffer);
  bytes.set([0x45, 0x53, 0x50, 0x46, 1, 1]);
  const view = new DataView(buffer);
  view.setUint16(6, width);
  view.setUint16(8, height);
  view.setUint32(10, 12);
  bytes.set(pixels, 14);
  return buffer;
}

describe("parseFramebufferPacket", () => {
  it("parses the versioned RGB24 wire format", () => {
    const frame = parseFramebufferPacket(packet(2, 1, [255, 0, 0, 0, 0, 255]));

    expect(frame).toMatchObject({ sequence: 12, width: 2, height: 1 });
    expect([...frame.pixels]).toEqual([255, 0, 0, 0, 0, 255]);
  });

  it("rejects a short pixel payload", () => {
    expect(() => parseFramebufferPacket(packet(2, 1, [255, 0, 0]))).toThrow(
      FramebufferPacketError,
    );
  });
});
