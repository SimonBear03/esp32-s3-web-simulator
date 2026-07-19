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

  if (boardId === "cardputer-adv") {
    return (
      <div className="inspector-section empty-inspector">
        <BatteryCharging size={24} />
        <strong>Cardputer power model is planned</strong>
        <p>This profile currently exposes reset and persistent NVS, not battery telemetry.</p>
      </div>
    );
  }

  return (
    <div className="inspector-section">
      <div className="inspector-title">
        <BatteryCharging size={17} />
        <span>M5PM1 behavioral state</span>
      </div>
      <label className="range-field">
        <span>
          Battery <code>{sample.battery_mv} mV</code>
        </span>
        <input
          disabled={!enabled}
          max={6000}
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
      <button
        className="secondary-button apply-button"
        disabled={!enabled}
        onClick={() => onPower(sample)}
        type="button"
      >
        <BatteryCharging size={15} />
        Apply power state
      </button>
      <p className="field-help">Logical I2C telemetry only; this is not electrical measurement.</p>
    </div>
  );
}
