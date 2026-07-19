// SPDX-License-Identifier: GPL-2.0-only

import { Activity, Keyboard } from "lucide-react";
import { useState } from "react";

import type { BoardId, ImuSample } from "../../lib/types";
import { VectorFields } from "./VectorFields";

interface InputInspectorProps {
  boardId: BoardId;
  enabled: boolean;
  onButton: (button: "a" | "b", pressed: boolean) => void;
  onImu: (sample: ImuSample) => void;
}

const INITIAL_IMU: ImuSample = {
  acceleration_g: { x: 0, y: 0, z: 1 },
  angular_velocity_dps: { x: 0, y: 0, z: 0 },
};

export function InputInspector({
  boardId,
  enabled,
  onButton,
  onImu,
}: InputInspectorProps) {
  const [imu, setImu] = useState<ImuSample>(INITIAL_IMU);

  return (
    <div
      className={`inspector-section${
        boardId === "cardputer-adv" ? " input-overview" : ""
      }`}
    >
      {boardId === "cardputer-adv" ? (
        <>
          <div className="inspector-title">
            <Keyboard size={17} />
            <span>Keyboard matrix</span>
          </div>
          <p>
            Click the virtual keys or type while the device stage is focused. Key
            transitions enter the emulated TCA8418 FIFO and GPIO interrupt path.
          </p>
          <div className="signal-path" aria-label="Keyboard emulation signal path">
            <span>Browser key</span>
            <i aria-hidden="true" />
            <span>TCA8418</span>
            <i aria-hidden="true" />
            <span>GPIO 11</span>
          </div>
          <div className="inspector-note" data-active={enabled}>
            {enabled ? "Keyboard input connected" : "Run a session to send keys"}
          </div>
        </>
      ) : (
        <>
          <div className="inspector-title">
            <Activity size={17} />
            <span>Runtime inputs</span>
          </div>
          <div className="button-inputs">
            {(["a", "b"] as const).map((button) => (
              <div key={button}>
                <span>Button {button.toUpperCase()}</span>
                <button
                  className="secondary-button"
                  disabled={!enabled}
                  onPointerCancel={() => onButton(button, false)}
                  onPointerDown={() => onButton(button, true)}
                  onPointerUp={() => onButton(button, false)}
                  type="button"
                >
                  Press
                </button>
              </div>
            ))}
          </div>
        </>
      )}
      {boardId === "cardputer-adv" ? (
        <div className="inspector-title motion-input-title">
          <Activity size={17} />
          <span>BMI270 motion</span>
        </div>
      ) : null}
      <VectorFields
        disabled={!enabled}
        legend="Acceleration"
        max={16}
        min={-16}
        onChange={(acceleration_g) => setImu((current) => ({ ...current, acceleration_g }))}
        step={0.01}
        unit="g"
        value={imu.acceleration_g}
      />
      <VectorFields
        disabled={!enabled}
        legend="Angular velocity"
        max={2000}
        min={-2000}
        onChange={(angular_velocity_dps) =>
          setImu((current) => ({ ...current, angular_velocity_dps }))
        }
        step={1}
        unit="dps"
        value={imu.angular_velocity_dps}
      />
      <button
        className="secondary-button apply-button"
        disabled={!enabled}
        onClick={() => onImu(imu)}
        type="button"
      >
        <Activity size={15} />
        Apply sample
      </button>
      <p className="field-help">
        BMI270 samples use physical units and are clamped to ±16 g and ±2000 dps.
      </p>
    </div>
  );
}
