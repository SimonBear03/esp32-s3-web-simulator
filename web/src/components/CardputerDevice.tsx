// SPDX-License-Identifier: GPL-2.0-only

import {
  type CSSProperties,
  useCallback,
  useEffect,
  useState,
} from "react";

import { boardKeyFromDomKey, CARDPUTER_KEY_ROWS } from "../lib/keyboard";
import { DisplayCanvas } from "./DisplayCanvas";

interface CardputerDeviceProps {
  sessionId: string | null;
  streamGeneration: number;
  inputEnabled: boolean;
  onKey: (key: string, pressed: boolean) => void;
}

function updatePressedKey(
  current: Set<string>,
  key: string,
  pressed: boolean,
): Set<string> {
  const next = new Set(current);
  if (pressed) next.add(key);
  else next.delete(key);
  return next;
}

export function CardputerDevice({
  sessionId,
  streamGeneration,
  inputEnabled,
  onKey,
}: CardputerDeviceProps) {
  const [pressedKeys, setPressedKeys] = useState<Set<string>>(() => new Set());

  const emitKey = useCallback(
    (key: string, pressed: boolean) => {
      if (!inputEnabled) return;
      setPressedKeys((current) => updatePressedKey(current, key, pressed));
      onKey(key, pressed);
    },
    [inputEnabled, onKey],
  );

  useEffect(() => {
    if (!inputEnabled) {
      setPressedKeys(new Set());
      return;
    }
    const held = new Set<string>();
    const ignoredTarget = (target: EventTarget | null) =>
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement;
    const onKeyDown = (event: KeyboardEvent) => {
      if (ignoredTarget(event.target) || event.repeat) return;
      const key = boardKeyFromDomKey(event.key);
      if (!key) return;
      event.preventDefault();
      held.add(key);
      emitKey(key, true);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      const key = boardKeyFromDomKey(event.key);
      if (!key || !held.has(key)) return;
      held.delete(key);
      emitKey(key, false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      for (const key of held) onKey(key, false);
    };
  }, [emitKey, inputEnabled, onKey]);

  return (
    <div className="cardputer-device" data-input-enabled={inputEnabled}>
      <div className="device-screw screw-nw" aria-hidden="true" />
      <div className="device-screw screw-ne" aria-hidden="true" />
      <div className="device-screw screw-sw" aria-hidden="true" />
      <div className="device-screw screw-se" aria-hidden="true" />
      <div className="cardputer-screen-bezel">
        <DisplayCanvas
          boardLabel="Cardputer ADV compatible"
          height={135}
          sessionId={sessionId}
          streamGeneration={streamGeneration}
          width={240}
        />
      </div>
      <div className="cardputer-keyboard" aria-label="Virtual Cardputer keyboard">
        {CARDPUTER_KEY_ROWS.map((row, rowIndex) => (
          <div className="keyboard-row" key={rowIndex}>
            {row.map((key) => (
              <button
                className="device-key"
                data-pressed={pressedKeys.has(key.id)}
                disabled={!inputEnabled}
                key={key.id}
                onPointerCancel={() => emitKey(key.id, false)}
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture(event.pointerId);
                  emitKey(key.id, true);
                }}
                onPointerUp={() => emitKey(key.id, false)}
                style={{ "--key-width": key.width ?? 1 } as CSSProperties}
                type="button"
              >
                {key.label}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
