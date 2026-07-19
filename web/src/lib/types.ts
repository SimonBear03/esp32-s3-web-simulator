// SPDX-License-Identifier: GPL-2.0-only

export type BoardId = "cardputer-adv" | "sticks3";
export type SessionState =
  | "starting"
  | "running"
  | "paused"
  | "stopped"
  | "failed"
  | "expired";

export interface Capability {
  id: string;
  label: string;
  fidelity: "emulated" | "behavioral" | "planned" | "unsupported";
  note: string;
}

export interface DisplayProfile {
  controller: string;
  width: number;
  height: number;
  transport: string;
  rotation_degrees: number;
}

export interface BoardProfile {
  id: BoardId;
  label: string;
  mcu: string;
  flash_size_bytes: number;
  psram_size_mib: number;
  display: DisplayProfile;
  capabilities: Capability[];
}

export interface FirmwareMetadata {
  source_size_bytes: number;
  flash_size_bytes: number;
  source_sha256: string;
  flash_sha256: string;
  segment_count: number;
  flash_mode: number;
}

export interface SimulationSession {
  id: string;
  board_id: BoardId;
  state: SessionState;
  created_at: string;
  expires_at: string;
  exit_code: number | null;
  firmware: FirmwareMetadata;
}

export interface DebugCapabilities {
  register_read: boolean;
  memory_read_max_bytes: number;
  hardware_breakpoints_max: number;
  single_step: boolean;
  memory_write: false;
  register_write: false;
  raw_gdb: false;
}

export interface DebugStatus {
  state: SessionState;
  stop_reason: string | null;
  enabled: boolean;
  capabilities: DebugCapabilities;
}

export interface MemoryRead {
  address: number;
  length: number;
  data_hex: string;
}

export interface Vector3 {
  x: number;
  y: number;
  z: number;
}

export interface ImuSample {
  acceleration_g: Vector3;
  angular_velocity_dps: Vector3;
}

export interface PowerSample {
  battery_mv: number;
  vin_mv: number;
  charging: boolean;
}

export type InputEvent =
  | { type: "key"; key: string; pressed: boolean; sequence?: number }
  | { type: "button"; button: "a" | "b"; pressed: boolean; sequence?: number }
  | ({ type: "imu"; sequence?: number } & ImuSample)
  | ({ type: "power"; sequence?: number } & PowerSample);

export interface FramebufferFrame {
  sequence: number;
  width: number;
  height: number;
  pixels: Uint8Array;
}
