// SPDX-License-Identifier: GPL-2.0-only

import { useEffect, useState } from "react";

import type {
  BoardId,
  ImuSample,
  InputEvent,
  PowerSample,
  SimulationSession,
} from "../lib/types";
import { DebugInspector } from "./debug/DebugInspector";
import { InputInspector } from "./inspector/InputInspector";
import { PowerInspector } from "./inspector/PowerInspector";
import { TimelineInspector } from "./inspector/TimelineInspector";

export type InspectorTab = "inputs" | "debug" | "power" | "timeline";

type InputEventWithoutSequence = InputEvent extends infer Event
  ? Event extends InputEvent
    ? Omit<Event, "sequence">
    : never
  : never;

interface InspectorProps {
  boardId: BoardId;
  session: SimulationSession | null;
  inputConnected: boolean;
  sendBoardInput: (event: InputEventWithoutSequence) => boolean;
}

const TABS: { id: InspectorTab; label: string }[] = [
  { id: "inputs", label: "Inputs" },
  { id: "debug", label: "Debug" },
  { id: "power", label: "Power" },
  { id: "timeline", label: "Timeline" },
];

export function Inspector({
  boardId,
  session,
  inputConnected,
  sendBoardInput,
}: InspectorProps) {
  const [tab, setTab] = useState<InspectorTab>("inputs");
  const inputEnabled = session?.state === "running" && inputConnected;
  const tabs = session?.anonymous
    ? TABS.filter((candidate) => candidate.id === "inputs" || candidate.id === "power")
    : TABS;

  useEffect(() => {
    if (session?.anonymous && (tab === "debug" || tab === "timeline")) {
      setTab("inputs");
    }
  }, [session?.anonymous, tab]);

  function sendImu(sample: ImuSample) {
    sendBoardInput({ type: "imu", ...sample });
  }

  function sendPower(sample: PowerSample) {
    sendBoardInput({ type: "power", ...sample });
  }

  return (
    <aside className="inspector" aria-label="Simulator inspector">
      <div className="inspector-tabs" role="tablist" aria-label="Inspector mode">
        {tabs.map((candidate) => (
          <button
            aria-selected={tab === candidate.id}
            className="inspector-tab"
            key={candidate.id}
            onClick={() => setTab(candidate.id)}
            role="tab"
            type="button"
          >
            {candidate.label}
          </button>
        ))}
      </div>
      <div className="inspector-body">
        {tab === "inputs" ? (
          <InputInspector
            boardId={boardId}
            enabled={inputEnabled}
            onButton={(button, pressed) =>
              sendBoardInput({ type: "button", button, pressed })
            }
            onImu={sendImu}
          />
        ) : null}
        {tab === "debug" ? <DebugInspector session={session} /> : null}
        {tab === "power" ? (
          <PowerInspector
            boardId={boardId}
            enabled={inputEnabled}
            onPower={sendPower}
          />
        ) : null}
        {tab === "timeline" ? <TimelineInspector session={session} /> : null}
      </div>
    </aside>
  );
}
