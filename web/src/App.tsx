// SPDX-License-Identifier: GPL-2.0-only

import { ChevronDown, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AppHeader } from "./components/AppHeader";
import { DeviceStage } from "./components/DeviceStage";
import { FirmwarePanel } from "./components/FirmwarePanel";
import { HostedAccessGate } from "./components/HostedAccessGate";
import { Inspector } from "./components/Inspector";
import {
  MobilePanelNav,
  type MobilePanel,
} from "./components/MobilePanelNav";
import { SerialDock } from "./components/SerialDock";
import { StatusBar } from "./components/StatusBar";
import { useBoardProfiles } from "./hooks/useBoardProfiles";
import { useHostedAccess } from "./hooks/useHostedAccess";
import { useSavedApps } from "./hooks/useSavedApps";
import { useSimulatorSession } from "./hooks/useSimulatorSession";
import { shortBoardLabel } from "./lib/boards";
import type { ElfSymbolIndex } from "./lib/elf";
import type { BoardId } from "./lib/types";

export function App() {
  const boards = useBoardProfiles();
  const hostedAccess = useHostedAccess();
  const [boardId, setBoardId] = useState<BoardId>("cardputer-adv");
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>("device");
  const [setupOpen, setSetupOpen] = useState(false);
  const [debugSymbols, setDebugSymbols] = useState<ElfSymbolIndex | null>(null);
  const {
    session,
    busyAction,
    error,
    inputConnected,
    start,
    startSaved,
    pause,
    resume,
    reset,
    stop,
    sendBoardInput,
    clearError,
  } = useSimulatorSession();
  const savedAppsEnabled =
    hostedAccess.config?.access_kind === "account" &&
    hostedAccess.config.saved_apps_enabled === true;
  const savedApps = useSavedApps(savedAppsEnabled);
  const board = boards[boardId];
  const active = Boolean(
    session && ["starting", "running", "paused"].includes(session.state),
  );
  const sessionId = active && session ? session.id : null;
  const streamGeneration = active && session ? session.generation : 0;
  const inputEnabled = session?.state === "running" && inputConnected;

  useEffect(() => {
    if (
      debugSymbols &&
      session &&
      !["starting", "running", "paused"].includes(session.state)
    ) {
      setDebugSymbols(null);
    }
  }, [debugSymbols, session]);

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
        accountAccess={hostedAccess.config?.access_kind === "account"}
        onBoardChange={changeBoard}
        onPause={() => void pause()}
        onReset={() => void reset()}
        onResume={() => void resume()}
        onStop={() => {
          void stop().finally(() => setDebugSymbols(null));
        }}
        onSignOut={() => void hostedAccess.signOut()}
        signingOut={hostedAccess.submitting}
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

      <div
        className="workbench"
        data-mobile-panel={mobilePanel}
        data-mobile-setup-open={setupOpen}
      >
        <div className="setup-region" data-mobile-open={setupOpen}>
          <FirmwarePanel
            board={board}
            onStart={async (file, symbols) => {
              if (
                hostedAccess.state !== "standalone" &&
                hostedAccess.state !== "authorized"
              ) {
                return;
              }
              if (await start(boardId, file)) {
                setDebugSymbols(symbols);
                setSetupOpen(false);
                setMobilePanel("device");
              }
            }}
            onRunSaved={async (saved) => {
              if (active || (await startSaved(saved.id)) === false) return;
              setDebugSymbols(null);
              setBoardId(saved.board_id);
              setSetupOpen(false);
              setMobilePanel("device");
            }}
            savedApps={savedAppsEnabled ? savedApps : null}
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
            streamGeneration={streamGeneration}
          />
        </div>
        <div
          className="inspector-region"
          data-mobile-active={mobilePanel === "inspector"}
        >
          <Inspector
            boardId={boardId}
            debugSymbols={debugSymbols}
            inputConnected={inputConnected}
            sendBoardInput={sendBoardInput}
            session={session}
          />
        </div>
      </div>

      <div className="serial-region" data-mobile-active={mobilePanel === "serial"}>
        <SerialDock
          sessionId={sessionId}
          streamGeneration={streamGeneration}
          symbols={debugSymbols}
        />
      </div>
      <MobilePanelNav onChange={setMobilePanel} panel={mobilePanel} />
      <StatusBar inputConnected={inputConnected} expiresAt={session?.expires_at ?? null} />
      <HostedAccessGate access={hostedAccess} />
    </div>
  );
}
