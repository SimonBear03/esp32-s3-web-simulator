// SPDX-License-Identifier: GPL-2.0-only

import { useEffect, useState } from "react";

import { DisplayCanvas } from "./DisplayCanvas";

interface StickDeviceProps {
  sessionId: string | null;
  streamGeneration: number;
  inputEnabled: boolean;
  onButton: (button: "a" | "b", pressed: boolean) => void;
}

export function StickDevice({
  sessionId,
  streamGeneration,
  inputEnabled,
  onButton,
}: StickDeviceProps) {
  const [pressedButton, setPressedButton] = useState<"a" | "b" | null>(null);

  useEffect(() => {
    if (!inputEnabled) setPressedButton(null);
  }, [inputEnabled]);

  function emitButton(button: "a" | "b", pressed: boolean) {
    if (!inputEnabled) return;
    setPressedButton(pressed ? button : null);
    onButton(button, pressed);
  }

  return (
    <div className="stick-device" data-input-enabled={inputEnabled}>
      <div className="stick-top-detail" aria-hidden="true" />
      <div className="stick-screen-bezel">
        <DisplayCanvas
          boardLabel="StickS3 compatible"
          height={240}
          sessionId={sessionId}
          streamGeneration={streamGeneration}
          width={135}
        />
      </div>
      <div className="stick-buttons" aria-label="Virtual StickS3 buttons">
        {(["a", "b"] as const).map((button) => (
          <button
            className="stick-button"
            data-pressed={pressedButton === button}
            disabled={!inputEnabled}
            key={button}
            onPointerCancel={() => emitButton(button, false)}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              emitButton(button, true);
            }}
            onPointerUp={() => emitButton(button, false)}
            type="button"
          >
            {button.toUpperCase()}
          </button>
        ))}
      </div>
      <div className="stick-port" aria-hidden="true" />
    </div>
  );
}
