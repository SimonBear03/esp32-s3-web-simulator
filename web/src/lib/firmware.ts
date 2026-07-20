// SPDX-License-Identifier: GPL-2.0-only

import type { BoardProfile } from "./types";

const ESP_IMAGE_MAGIC = 0xe9;
const MINIMUM_IMAGE_SIZE = 4096;
const MAXIMUM_SEGMENTS = 16;
const ESP_APP_DESC_MAGIC = 0xabcd5432;
const ESP_APP_DESC_OFFSET = 0x20;
const ESP_APP_ELF_SHA256_OFFSET = 144;
const SHA256_BYTES = 32;
const MAX_FIRMWARE_BUILD_MATCH_BYTES = 8 * 1024 * 1024;

export type ElfFirmwareMatch = "matched" | "mismatched" | "unavailable";

export interface FirmwareCheck {
  label: string;
  value: string;
  valid: boolean;
}

export interface FirmwareInspection {
  valid: boolean;
  checks: FirmwareCheck[];
  segmentCount: number | null;
  flashMode: number | null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${kib.toFixed(kib >= 100 ? 0 : 1)} KiB`;
  const mib = kib / 1024;
  return `${mib.toFixed(mib >= 10 ? 1 : 2)} MiB`;
}

function hex(bytes: Uint8Array): string {
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

export async function embeddedElfHashes(file: File): Promise<Set<string>> {
  if (file.size > MAX_FIRMWARE_BUILD_MATCH_BYTES) {
    throw new Error("Firmware is too large for browser build matching");
  }
  const payload = new Uint8Array(await file.arrayBuffer());
  const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const hashes = new Set<string>();
  const descriptorBytes = ESP_APP_ELF_SHA256_OFFSET + SHA256_BYTES;
  for (
    let appOffset = 0;
    appOffset + ESP_APP_DESC_OFFSET + descriptorBytes <= payload.length;
    appOffset += 4
  ) {
    if (
      payload[appOffset] !== ESP_IMAGE_MAGIC ||
      payload[appOffset + 1] < 1 ||
      payload[appOffset + 1] > MAXIMUM_SEGMENTS ||
      payload[appOffset + 2] > 3
    ) {
      continue;
    }
    const descriptorOffset = appOffset + ESP_APP_DESC_OFFSET;
    if (view.getUint32(descriptorOffset, true) !== ESP_APP_DESC_MAGIC) continue;
    const digest = payload.subarray(
      descriptorOffset + ESP_APP_ELF_SHA256_OFFSET,
      descriptorOffset + ESP_APP_ELF_SHA256_OFFSET + SHA256_BYTES,
    );
    if (digest.every((value) => value === 0 || value === 0xff)) continue;
    hashes.add(hex(digest));
  }
  return hashes;
}

export async function verifyElfFirmwareMatch(
  firmware: File,
  elfSha256: string,
): Promise<ElfFirmwareMatch> {
  const hashes = await embeddedElfHashes(firmware);
  if (hashes.size === 0) return "unavailable";
  return hashes.has(elfSha256) ? "matched" : "mismatched";
}

export async function inspectFirmware(
  file: File,
  board: BoardProfile,
): Promise<FirmwareInspection> {
  const header = new Uint8Array(await file.slice(0, 4).arrayBuffer());
  const segmentCount = header.length >= 2 ? header[1] : null;
  const flashMode = header.length >= 3 ? header[2] : null;
  const checks: FirmwareCheck[] = [
    {
      label: "Merged image header",
      value: header[0] === ESP_IMAGE_MAGIC ? "0xE9" : "Not an ESP image",
      valid: header[0] === ESP_IMAGE_MAGIC,
    },
    {
      label: "Image size",
      value: formatBytes(file.size),
      valid: file.size >= MINIMUM_IMAGE_SIZE,
    },
    {
      label: "Board flash fit",
      value: `${formatBytes(file.size)} / ${formatBytes(board.flash_size_bytes)}`,
      valid: file.size <= board.flash_size_bytes,
    },
    {
      label: "Segment count",
      value: segmentCount === null ? "Unavailable" : String(segmentCount),
      valid:
        segmentCount !== null &&
        segmentCount >= 1 &&
        segmentCount <= MAXIMUM_SEGMENTS,
    },
    {
      label: "Flash mode",
      value: flashMode === null ? "Unavailable" : `mode ${flashMode}`,
      valid: flashMode !== null && flashMode <= 3,
    },
  ];

  return {
    valid: checks.every((check) => check.valid),
    checks,
    segmentCount,
    flashMode,
  };
}
