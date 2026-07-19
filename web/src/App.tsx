// SPDX-License-Identifier: GPL-2.0-only

import { ChevronDown, X } from "lucide-react";
import { useCallback, useState } from "react";

import { AppHeader } from "./components/AppHeader";
import { DeviceStage } from "./components/DeviceStage";
import { FirmwarePanel } from "./components/FirmwarePanel";
import { Inspector } from "./components/Inspector";
import {
  MobilePanelNav,
  type MobilePanel,
} from "./components/MobilePanelNav";
import { SerialDock } from "./components/SerialDock";
import { StatusBar } from "./components/StatusBar";
import { useBoardProfiles } from "./hooks/useBoardProfiles";
import { useSimulatorSession } from "./hooks/useSimulatorSession";
import { shortBoardLabel } from "./lib/boards";
import type { BoardId } from "./lib/types";

export function App() {
  const boards = useBoardProfiles();
  const [boardId, setBoardId] = useState<BoardId>("cardputer-adv");
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("device");
  const [setupOpen, setSetupOpen] = useState(false);
  const {
    session,
    busyAction,
    error,
    inputConnected,
    start,
    pause,
    resume,
    reset,
    stop,
    sendBoardInput,
    clearError,
  } = useSimulatorSession();
  const board = boards[boardId];
  const active = Boolean(
    session && ["starting", "running", "paused"].includes(session.state),
  );
  const sessionId = active && session ? session.id : null;
  const inputEnabled = session?.state === "running" && inputConnected;

  const onKey = useCallback(
    (key: string, pressed: boolean) => {
      sendBoardInput({ type: "key", key, pressed });
    },
    [sendBoardInput],
  );
  const onButton = useCallback(
    (button: "a" | "b", pressed: boolean) => {
      sendBoardInput({ type: "button", button, pressed });
    },
    [sendBoardInput],
  );

  function changeBoard(nextBoardId: BoardId) {
    if (active) return;
    setBoardId(nextBoardId);
  }

  return (
    <div className="app-shell">
      <AppHeader
        boardId={boardId}
        boardLocked={active}
        busy={busyAction !== null}
        onBoardChange={changeBoard}
        onPause={() => void pause()}
        onReset={() => void reset()}
        onResume={() => void resume()}
        onStop={() => void stop()}
        sessionState={session?.state ?? "idle"}
      />

      {error ? (
        <div className="global-error" role="alert">
          <span>{error}</span>
          <button aria-label="Dismiss error" onClick={clearError} type="button">
            <X size={15} />
          </button>
        </div>
      ) : null}

      <button
        aria-expanded={setupOpen}
        className="mobile-setup-toggle"
        onClick={() => setSetupOpen((value) => !value)}
        type="button"
      >
        <span>
          Firmware setup · {shortBoardLabel(boardId)}
        </span>
        <ChevronDown size={16} />
      </button>

      <div className="workbench" data-mobile-panel={mobilePanel}>
        <div className="setup-region" data-mobile-open={setupOpen}>
          <FirmwarePanel
            board={board}
            onStart={async (file) => {
              if (await start(boardId, file)) {
                setSetupOpen(false);
                setMobilePanel("device");
              }
            }}
            session={session}
            starting={busyAction === "start"}
          />
        </div>
        <div className="device-region" data-mobile-active={mobilePanel === "device"}>
          <DeviceStage
            boardId={boardId}
            inputEnabled={inputEnabled}
            onButton={onButton}
            onKey={onKey}
            sessionId={sessionId}
          />
        </div>
        <div
          className="inspector-region"
          data-mobile-active={mobilePanel === "inspector"}
        >
          <Inspector
            boardId={boardId}
            inputConnected={inputConnected}
            sendBoardInput={sendBoardInput}
            session={session}
          />
        </div>
      </div>

      <div className="serial-region" data-mobile-active={mobilePanel === "serial"}>
        <SerialDock sessionId={sessionId} />
      </div>
      <MobilePanelNav onChange={setMobilePanel} panel={mobilePanel} />
      <StatusBar inputConnected={inputConnected} expiresAt={session?.expires_at ?? null} />
    </div>
  );
}
