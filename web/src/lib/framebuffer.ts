// SPDX-License-Identifier: GPL-2.0-only

import type { FramebufferFrame } from "./types";

const HEADER_SIZE = 14;
const MAGIC = "ESPF";

export class FramebufferPacketError extends Error {}

export function parseFramebufferPacket(buffer: ArrayBuffer): FramebufferFrame {
  if (buffer.byteLength < HEADER_SIZE) {
    throw new FramebufferPacketError("framebuffer packet is shorter than its header");
  }
  const bytes = new Uint8Array(buffer);
  const magic = String.fromCharCode(...bytes.slice(0, 4));
  const view = new DataView(buffer);
  const version = view.getUint8(4);
  const pixelFormat = view.getUint8(5);
  const width = view.getUint16(6);
  const height = view.getUint16(8);
  const sequence = view.getUint32(10);
  if (magic !== MAGIC || version !== 1 || pixelFormat !== 1) {
    throw new FramebufferPacketError("unsupported framebuffer packet format");
  }
  const pixels = bytes.slice(HEADER_SIZE);
  if (pixels.length !== width * height * 3) {
    throw new FramebufferPacketError("framebuffer packet has an invalid pixel length");
  }
  return { sequence, width, height, pixels };
}

export function paintFramebuffer(
  canvas: HTMLCanvasElement,
  frame: FramebufferFrame,
): void {
  if (canvas.width !== frame.width || canvas.height !== frame.height) {
    canvas.width = frame.width;
    canvas.height = frame.height;
  }
  const context = canvas.getContext("2d");
  if (!context) return;
  const rgba = new Uint8ClampedArray(frame.width * frame.height * 4);
  for (let source = 0, target = 0; source < frame.pixels.length; source += 3) {
    rgba[target] = frame.pixels[source];
    rgba[target + 1] = frame.pixels[source + 1];
    rgba[target + 2] = frame.pixels[source + 2];
    rgba[target + 3] = 255;
    target += 4;
  }
  context.putImageData(new ImageData(rgba, frame.width, frame.height), 0, 0);
}
