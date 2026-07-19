// SPDX-License-Identifier: GPL-2.0-only

import type {
  BoardProfile,
  DebugStatus,
  InputEvent,
  MemoryRead,
  ReplayStatus,
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
  return (await response.json()) as T;
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

export function getSession(sessionId: string): Promise<SimulationSession> {
  return request(`/v1/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string): Promise<SimulationSession> {
  return request(`/v1/sessions/${sessionId}`, { method: "DELETE" });
}

export function controlSession(
  sessionId: string,
  action: "pause" | "resume" | "reset",
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
