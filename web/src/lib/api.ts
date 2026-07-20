// SPDX-License-Identifier: GPL-2.0-only

import type {
  BoardProfile,
  DebugStatus,
  HostedAccessConfig,
  AnonymousHeartbeat,
  InputEvent,
  HostedLoginResult,
  MemoryRead,
  ReplayStatus,
  SavedApp,
  SavedAppList,
  SessionEventPage,
  SimulationSession,
} from "./types";

const configuredBase = import.meta.env.VITE_SIMULATOR_API_BASE?.trim() ?? "";
const API_BASE = configuredBase.replace(/\/$/, "");

export class SimulatorApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let detail = `Simulator request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the bounded status-only fallback when the gateway did not return JSON.
    }
    throw new SimulatorApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function isHostedAccessConfig(value: unknown): value is HostedAccessConfig {
  if (!value || typeof value !== "object") return false;
  const config = value as Partial<HostedAccessConfig>;
  return (
    typeof config.enabled === "boolean" &&
    typeof config.authorized === "boolean" &&
    typeof config.capability === "boolean" &&
    (config.access_kind === "account" ||
      config.access_kind === "anonymous" ||
      config.access_kind === null) &&
    (typeof config.site_key === "string" || config.site_key === null) &&
    (typeof config.action === "string" || config.action === null) &&
    (typeof config.heartbeat_interval_seconds === "number" ||
      config.heartbeat_interval_seconds === null) &&
    (typeof config.session_lifetime_seconds === "number" ||
      config.session_lifetime_seconds === null) &&
    (typeof config.saved_apps_enabled === "boolean" ||
      config.saved_apps_enabled === undefined) &&
    (typeof config.saved_app_limit === "number" ||
      config.saved_app_limit === null ||
      config.saved_app_limit === undefined) &&
    (config.auth_mode === "local" ||
      config.auth_mode === "supabase" ||
      config.auth_mode === undefined) &&
    (typeof config.anonymous_enabled === "boolean" ||
      config.anonymous_enabled === undefined) &&
    (typeof config.supabase_url === "string" ||
      config.supabase_url === null ||
      config.supabase_url === undefined) &&
    (typeof config.supabase_publishable_key === "string" ||
      config.supabase_publishable_key === null ||
      config.supabase_publishable_key === undefined)
  );
}

export function exchangeSupabaseSession(accessToken: string): Promise<HostedLoginResult> {
  return request("/auth/exchange", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function logoutHostedSession(): Promise<void> {
  return request("/auth/logout", { method: "POST" });
}

export async function getHostedAccessConfig(
  signal?: AbortSignal,
): Promise<HostedAccessConfig | null> {
  const endpoint = new URL(`${API_BASE}/anonymous/config`, window.location.origin);
  if (endpoint.origin !== window.location.origin) return null;
  const response = await fetch(endpoint, { credentials: "same-origin", signal });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new SimulatorApiError(
      `Hosted access check failed (${response.status})`,
      response.status,
    );
  }
  const value: unknown = await response.json();
  if (!isHostedAccessConfig(value)) {
    throw new SimulatorApiError("Hosted access returned an invalid response", 502);
  }
  return value;
}

export function createAnonymousCapability(token: string): Promise<{
  anonymous: true;
  expires_at: number;
}> {
  return request("/anonymous/capabilities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
}

export function heartbeatAnonymousSession(
  sessionId: string,
): Promise<AnonymousHeartbeat> {
  return request(`/v1/sessions/${sessionId}/heartbeat`, { method: "POST" });
}

export function listBoards(signal?: AbortSignal): Promise<BoardProfile[]> {
  return request("/v1/boards", { signal });
}

export function createSession(
  boardId: string,
  firmware: File,
): Promise<SimulationSession> {
  const data = new FormData();
  data.set("board_id", boardId);
  data.set("firmware", firmware, firmware.name);
  return request("/v1/sessions", { method: "POST", body: data });
}

export function listSavedApps(signal?: AbortSignal): Promise<SavedAppList> {
  return request("/v1/saved-apps", { signal });
}

function savedAppPath(
  path: string,
  name: string,
  boardId: string,
): string {
  const query = new URLSearchParams({ name, board_id: boardId });
  return `${path}?${query}`;
}

export function createSavedApp(
  name: string,
  boardId: string,
  firmware: File,
): Promise<SavedApp> {
  return request(savedAppPath("/v1/saved-apps", name, boardId), {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: firmware,
  });
}

export function replaceSavedApp(
  appId: string,
  name: string,
  boardId: string,
  firmware: File,
): Promise<SavedApp> {
  return request(savedAppPath(`/v1/saved-apps/${appId}`, name, boardId), {
    method: "PUT",
    headers: { "Content-Type": "application/octet-stream" },
    body: firmware,
  });
}

export function renameSavedApp(appId: string, name: string): Promise<SavedApp> {
  return request(`/v1/saved-apps/${appId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function deleteSavedApp(appId: string): Promise<void> {
  return request(`/v1/saved-apps/${appId}`, { method: "DELETE" });
}

export function runSavedApp(appId: string): Promise<SimulationSession> {
  return request(`/v1/saved-apps/${appId}/sessions`, { method: "POST" });
}

export function getSession(sessionId: string): Promise<SimulationSession> {
  return request(`/v1/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string): Promise<SimulationSession> {
  return request(`/v1/sessions/${sessionId}`, { method: "DELETE" });
}

export function controlSession(
  sessionId: string,
  action: "pause" | "resume" | "reset" | "power-off" | "power-on",
): Promise<SimulationSession> {
  return request(`/v1/sessions/${sessionId}/control`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
}

export function getDebugStatus(sessionId: string): Promise<DebugStatus> {
  return request(`/v1/sessions/${sessionId}/debug/status`);
}

export async function getRegisters(
  sessionId: string,
): Promise<Record<string, number | null>> {
  const response = await request<{ registers: Record<string, number | null> }>(
    `/v1/sessions/${sessionId}/debug/registers`,
  );
  return response.registers;
}

export function readMemory(
  sessionId: string,
  address: number,
  length: number,
): Promise<MemoryRead> {
  return request(`/v1/sessions/${sessionId}/debug/memory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, length }),
  });
}

export function setBreakpoint(
  sessionId: string,
  address: number,
  enabled: boolean,
): Promise<{ address: number; enabled: boolean }> {
  return request(`/v1/sessions/${sessionId}/debug/breakpoint`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, enabled }),
  });
}

export function stepSession(sessionId: string): Promise<{ stop_reason: string }> {
  return request(`/v1/sessions/${sessionId}/debug/step`, { method: "POST" });
}

export function getSessionEvents(
  sessionId: string,
  after = 0,
  limit = 200,
): Promise<SessionEventPage> {
  const query = new URLSearchParams({ after: String(after), limit: String(limit) });
  return request(`/v1/sessions/${sessionId}/events?${query}`);
}

export function replaySession(sessionId: string, speed = 1): Promise<ReplayStatus> {
  return request(`/v1/sessions/${sessionId}/replay`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speed }),
  });
}

export function diagnosticsUrl(sessionId: string): string {
  return `${API_BASE}/v1/sessions/${sessionId}/diagnostics`;
}

function websocketUrl(path: string): string {
  const base = API_BASE || window.location.origin;
  const url = new URL(`${base}${path}`, window.location.origin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export function openSessionSocket(
  sessionId: string,
  channel: "serial" | "input" | "framebuffer",
): WebSocket {
  return new WebSocket(websocketUrl(`/v1/sessions/${sessionId}/${channel}`));
}

export function sendInput(socket: WebSocket | null, event: InputEvent): boolean {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(event));
  return true;
}
