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
  generation: number;
  recording: RecordingSummary;
  replay: ReplaySummary;
  anonymous?: boolean;
  heartbeat_interval_seconds?: number;
}

export interface HostedAccessConfig {
  enabled: boolean;
  anonymous_enabled?: boolean;
  authorized: boolean;
  access_kind: "account" | "anonymous" | null;
  capability: boolean;
  site_key: string | null;
  action: string | null;
  heartbeat_interval_seconds: number | null;
  session_lifetime_seconds: number | null;
  saved_apps_enabled?: boolean;
  saved_app_limit?: number | null;
  auth_mode?: "local" | "supabase";
  supabase_url?: string | null;
  supabase_publishable_key?: string | null;
}

export interface HostedLoginResult {
  authenticated: true;
  auth_provider: "supabase";
  username: string;
  expires_at: number;
}

export interface SavedApp {
  id: string;
  name: string;
  board_id: BoardId;
  source_size_bytes: number;
  created_at: string;
  updated_at: string;
}

export interface SavedAppList {
  apps: SavedApp[];
  limit: number;
}

export interface AnonymousHeartbeat {
  alive: boolean;
  expires_at: number;
  hard_expires_at: number;
  heartbeat_deadline: number;
}

export interface RecordingSummary {
  event_count: number;
  events_dropped: number;
  replayable_action_count: number;
  replayable_actions_dropped: number;
  trace_events_recorded: number;
  trace_events_dropped: number;
}

export interface ReplaySummary {
  status: "idle" | "queued" | "running" | "completed" | "failed" | "cancelled";
  speed: number | null;
  error: string | null;
}

export interface ReplayStatus extends ReplaySummary {
  session_id: string;
  generation: number;
  action_count: number;
  actions_dropped: number;
}

export interface SessionEvent {
  sequence: number;
  generation: number;
  offset_ms: number;
  category: "lifecycle" | "control" | "input" | "debug" | "replay" | "peripheral";
  type: string;
  source: "service" | "user" | "replay" | "worker";
  data: Record<string, unknown>;
}

export interface SessionEventPage {
  session_id: string;
  generation: number;
  events_dropped: number;
  cursor_truncated: boolean;
  events: SessionEvent[];
  next_after: number;
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
