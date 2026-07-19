// SPDX-License-Identifier: GPL-2.0-only

import { BatteryCharging } from "lucide-react";
import { useState } from "react";

import type { BoardId, PowerSample } from "../../lib/types";

interface PowerInspectorProps {
  boardId: BoardId;
  enabled: boolean;
  onPower: (sample: PowerSample) => void;
}

export function PowerInspector({
  boardId,
  enabled,
  onPower,
}: PowerInspectorProps) {
  const [sample, setSample] = useState<PowerSample>({
    battery_mv: 3900,
    vin_mv: 5000,
    charging: true,
  });

  return (
    <div className="inspector-section">
      <div className="inspector-title">
        <BatteryCharging size={17} />
        <span>
          {boardId === "cardputer-adv"
            ? "ADC battery state"
            : "M5PM1 behavioral state"}
        </span>
      </div>
      <label className="range-field">
        <span>
          Battery <code>{sample.battery_mv} mV</code>
        </span>
        <input
          disabled={!enabled}
          max={boardId === "cardputer-adv" ? 4300 : 6000}
          min={0}
          onChange={(event) =>
            setSample((current) => ({
              ...current,
              battery_mv: Number(event.target.value),
            }))
          }
          step={10}
          type="range"
          value={sample.battery_mv}
        />
      </label>
      {boardId === "sticks3" ? (
        <label className="range-field">
          <span>
            VIN <code>{sample.vin_mv} mV</code>
          </span>
          <input
            disabled={!enabled}
            max={6000}
            min={0}
            onChange={(event) =>
              setSample((current) => ({
                ...current,
                vin_mv: Number(event.target.value),
              }))
            }
            step={10}
            type="range"
            value={sample.vin_mv}
          />
        </label>
      ) : null}
      {boardId === "sticks3" ? (
        <label className="switch-field">
          <span>Charging</span>
          <input
            checked={sample.charging}
            disabled={!enabled}
            onChange={(event) =>
              setSample((current) => ({
                ...current,
                charging: event.target.checked,
              }))
            }
            type="checkbox"
          />
          <i aria-hidden="true" />
        </label>
      ) : null}
      <button
        className="secondary-button apply-button"
        disabled={!enabled}
        onClick={() =>
          onPower(
            boardId === "cardputer-adv"
              ? { ...sample, vin_mv: 0, charging: false }
              : sample,
          )
        }
        type="button"
      >
        <BatteryCharging size={15} />
        Apply power state
      </button>
      <p className="field-help">
        {boardId === "cardputer-adv"
          ? "ADC1/GPIO10 divider voltage; ADV hardware does not expose charging status or current."
          : "Logical I2C telemetry only; this is not electrical measurement."}
      </p>
    </div>
  );
}
