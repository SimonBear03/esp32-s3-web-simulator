// SPDX-License-Identifier: GPL-2.0-only

import type { BoardId, BoardProfile } from "./types";

export const FALLBACK_BOARDS: Record<BoardId, BoardProfile> = {
  "cardputer-adv": {
    id: "cardputer-adv",
    label: "Cardputer ADV compatible",
    mcu: "ESP32-S3FN8",
    flash_size_bytes: 8 * 1024 * 1024,
    psram_size_mib: 0,
    display: {
      controller: "ST7789",
      width: 240,
      height: 135,
      transport: "SPI",
      rotation_degrees: 90,
    },
    capabilities: [],
  },
  sticks3: {
    id: "sticks3",
    label: "StickS3 compatible",
    mcu: "ESP32-S3-PICO-1-N8R8",
    flash_size_bytes: 8 * 1024 * 1024,
    psram_size_mib: 8,
    display: {
      controller: "ST7789",
      width: 135,
      height: 240,
      transport: "SPI",
      rotation_degrees: 0,
    },
    capabilities: [],
  },
};

export const BOARD_IDS: BoardId[] = ["cardputer-adv", "sticks3"];

export function shortBoardLabel(boardId: BoardId): string {
  return boardId === "cardputer-adv" ? "Cardputer ADV" : "StickS3";
}
