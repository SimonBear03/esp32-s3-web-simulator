// SPDX-License-Identifier: GPL-2.0-only

import { Maximize2, Minus, Plus } from "lucide-react";
import { useState } from "react";

import type { BoardId } from "../lib/types";
import { CardputerDevice } from "./CardputerDevice";
import { StickDevice } from "./StickDevice";

interface DeviceStageProps {
  boardId: BoardId;
  sessionId: string | null;
  streamGeneration: number;
  inputEnabled: boolean;
  onKey: (key: string, pressed: boolean) => void;
  onButton: (button: "a" | "b", pressed: boolean) => void;
}

export function DeviceStage({
  boardId,
  sessionId,
  streamGeneration,
  inputEnabled,
  onKey,
  onButton,
}: DeviceStageProps) {
  const [zoom, setZoom] = useState(1);
  const deviceScale = boardId === "cardputer-adv" ? zoom : zoom * 0.92;

  return (
    <main className="device-stage" aria-label="Virtual device stage">
      <div className="ruler ruler-horizontal" aria-hidden="true">
        {[0, 50, 100, 150, 200, 250].map((tick) => (
          <span key={tick}>{tick}</span>
        ))}
        <small>mm</small>
      </div>
      <div className="ruler ruler-vertical" aria-hidden="true">
        {[0, 50, 100, 150, 200].map((tick) => (
          <span key={tick}>{tick}</span>
        ))}
      </div>
      <div className="device-stage-center">
        <div
          className="device-zoom-layer"
          style={{ transform: `scale(${deviceScale})` }}
        >
          {boardId === "cardputer-adv" ? (
            <CardputerDevice
              inputEnabled={inputEnabled}
              onKey={onKey}
              sessionId={sessionId}
              streamGeneration={streamGeneration}
            />
          ) : (
            <StickDevice
              inputEnabled={inputEnabled}
              onButton={onButton}
              sessionId={sessionId}
              streamGeneration={streamGeneration}
            />
          )}
        </div>
      </div>
      <div className="stage-toolbar" aria-label="Device stage zoom">
        <button
          aria-label="Fit device"
          className="icon-button"
          onClick={() => setZoom(1)}
          type="button"
        >
          <Maximize2 size={15} />
        </button>
        <span className="toolbar-divider" aria-hidden="true" />
        <button
          aria-label="Zoom out"
          className="icon-button"
          disabled={zoom <= 0.72}
          onClick={() => setZoom((value) => Math.max(0.7, value - 0.1))}
          type="button"
        >
          <Minus size={15} />
        </button>
        <output>{Math.round(zoom * 100)}%</output>
        <button
          aria-label="Zoom in"
          className="icon-button"
          disabled={zoom >= 1.22}
          onClick={() => setZoom((value) => Math.min(1.3, value + 0.1))}
          type="button"
        >
          <Plus size={15} />
        </button>
      </div>
    </main>
  );
}
