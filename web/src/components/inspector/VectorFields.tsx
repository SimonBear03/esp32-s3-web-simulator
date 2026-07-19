// SPDX-License-Identifier: GPL-2.0-only

import type { Vector3 } from "../../lib/types";

interface VectorFieldsProps {
  legend: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  value: Vector3;
  disabled: boolean;
  onChange: (value: Vector3) => void;
}

export function VectorFields({
  legend,
  unit,
  min,
  max,
  step,
  value,
  disabled,
  onChange,
}: VectorFieldsProps) {
  return (
    <fieldset className="vector-fields" disabled={disabled}>
      <legend>{legend}</legend>
      {(["x", "y", "z"] as const).map((axis) => (
        <label key={axis}>
          <span>{axis.toUpperCase()}</span>
          <input
            max={max}
            min={min}
            onChange={(event) =>
              onChange({ ...value, [axis]: Number(event.target.value) })
            }
            step={step}
            type="number"
            value={value[axis]}
          />
          <small>{unit}</small>
        </label>
      ))}
    </fieldset>
  );
}
