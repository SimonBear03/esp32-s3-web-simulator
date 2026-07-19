// SPDX-License-Identifier: GPL-2.0-only

import { useEffect, useState } from "react";

import { listBoards } from "../lib/api";
import { BOARD_IDS, FALLBACK_BOARDS } from "../lib/boards";
import type { BoardId, BoardProfile } from "../lib/types";

export function useBoardProfiles(): Record<BoardId, BoardProfile> {
  const [boards, setBoards] = useState<Record<BoardId, BoardProfile>>(
    () => FALLBACK_BOARDS,
  );

  useEffect(() => {
    const controller = new AbortController();
    void listBoards(controller.signal)
      .then((profiles) => {
        const next = { ...FALLBACK_BOARDS };
        for (const profile of profiles) next[profile.id] = profile;
        setBoards(next);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          // The local contract keeps setup usable while readiness is reported elsewhere.
        }
      });
    return () => controller.abort();
  }, []);

  return boards;
}

export function boardProfilesInDisplayOrder(
  boards: Record<BoardId, BoardProfile>,
): BoardProfile[] {
  return BOARD_IDS.map((boardId) => boards[boardId]);
}
