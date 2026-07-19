// SPDX-License-Identifier: GPL-2.0-only

import type { BoardProfile } from "./types";

const ESP_IMAGE_MAGIC = 0xe9;
const MINIMUM_IMAGE_SIZE = 4096;
const MAXIMUM_SEGMENTS = 16;

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
