// SPDX-License-Identifier: GPL-2.0-only

import {
  Cpu,
  LogOut,
  Pause,
  Play,
  RotateCw,
  Square,
} from "lucide-react";

import { shortBoardLabel } from "../lib/boards";
import type { BoardId, SessionState } from "../lib/types";

interface AppHeaderProps {
  boardId: BoardId;
  sessionState: SessionState | "idle";
  boardLocked: boolean;
  busy: boolean;
  onBoardChange: (boardId: BoardId) => void;
  onPause: () => void;
  onResume: () => void;
  onReset: () => void;
  onStop: () => void;
  accountAccess: boolean;
  onSignOut: () => void;
  signingOut: boolean;
}

const STATE_LABELS: Record<AppHeaderProps["sessionState"], string> = {
  idle: "Ready",
  starting: "Starting",
  running: "Running",
  paused: "Paused",
  powered_off: "Powered off",
  stopped: "Stopped",
  failed: "Failed",
  expired: "Expired",
};

export function AppHeader({
  boardId,
  sessionState,
  boardLocked,
  busy,
  onBoardChange,
  onPause,
  onResume,
  onReset,
  onStop,
  accountAccess,
  onSignOut,
  signingOut,
}: AppHeaderProps) {
  const active = ["starting", "running", "paused", "powered_off"].includes(
    sessionState,
  );
  const running = sessionState === "running";
  const paused = sessionState === "paused";
  const resettable = running || paused;

  return (
    <header className="app-header">
      <a className="brand" href="/" aria-label="ESP32-S3 Simulator home">
        <span className="brand-mark" aria-hidden="true">
          <Cpu size={20} strokeWidth={1.7} />
        </span>
        <span>ESP32-S3 Simulator</span>
      </a>

      <div className="header-board" aria-label="Virtual device profile">
        <span className="header-label">Board</span>
        {(["cardputer-adv", "sticks3"] as BoardId[]).map((candidate) => (
          <button
            className="board-segment"
            data-selected={boardId === candidate}
            disabled={boardLocked}
            key={candidate}
            onClick={() => onBoardChange(candidate)}
            type="button"
          >
            {shortBoardLabel(candidate)}
          </button>
        ))}
      </div>

      <div className="session-state" data-state={sessionState} aria-live="polite">
        <span className="header-label">Session</span>
        <span className="state-dot" aria-hidden="true" />
        <span>{STATE_LABELS[sessionState]}</span>
      </div>

      <div className="session-controls" aria-label="Simulation controls">
        <button
          className="tool-button"
          disabled={!paused || busy}
          onClick={onResume}
          type="button"
        >
          <Play size={15} fill="currentColor" />
          <span>Run</span>
        </button>
        <button
          className="tool-button"
          disabled={!running || busy}
          onClick={onPause}
          type="button"
        >
          <Pause size={15} fill="currentColor" />
          <span>Pause</span>
        </button>
        <button
          className="tool-button"
          disabled={!resettable || busy}
          onClick={onReset}
          type="button"
        >
          <RotateCw size={15} />
          <span>Reset</span>
        </button>
        <button
          className="tool-button"
          disabled={!active || busy}
          onClick={onStop}
          type="button"
        >
          <Square size={13} fill="currentColor" />
          <span>Stop</span>
        </button>
        {accountAccess ? (
          <button
            className="tool-button"
            disabled={active || busy || signingOut}
            onClick={onSignOut}
            type="button"
          >
            <LogOut size={14} />
            <span>Sign out</span>
          </button>
        ) : null}
      </div>
    </header>
  );
}
