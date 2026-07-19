// SPDX-License-Identifier: GPL-2.0-only

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import type { SimulationSession } from "../../lib/types";
import { TimelineInspector } from "./TimelineInspector";

const session: SimulationSession = {
  id: "a".repeat(32),
  board_id: "cardputer-adv",
  state: "running",
  created_at: "2026-07-19T00:00:00Z",
  expires_at: "2026-07-19T00:02:00Z",
  exit_code: null,
  firmware: {
    source_size_bytes: 4096,
    flash_size_bytes: 8 * 1024 * 1024,
    source_sha256: "b".repeat(64),
    flash_sha256: "c".repeat(64),
    segment_count: 1,
    flash_mode: 0,
  },
  generation: 1,
  recording: {
    event_count: 2,
    events_dropped: 0,
    replayable_action_count: 2,
    replayable_actions_dropped: 0,
    trace_events_recorded: 0,
    trace_events_dropped: 0,
  },
  replay: { status: "idle", speed: null, error: null },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows bounded events and starts an external-input replay", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/events?")) {
      return new Response(
        JSON.stringify({
          session_id: session.id,
          generation: 1,
          events_dropped: 0,
          cursor_truncated: false,
          next_after: 2,
          events: [
            {
              sequence: 1,
              generation: 1,
              offset_ms: 120,
              category: "input",
              type: "input.key",
              source: "user",
              data: { key: "a", pressed: true },
            },
            {
              sequence: 2,
              generation: 1,
              offset_ms: 150,
              category: "input",
              type: "input.key",
              source: "user",
              data: { key: "a", pressed: false },
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url.endsWith("/replay") && init?.method === "POST") {
      return new Response(
        JSON.stringify({
          session_id: session.id,
          generation: 1,
          status: "queued",
          speed: 1,
          error: null,
          action_count: 2,
          actions_dropped: 0,
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();

  render(<TimelineInspector session={session} />);

  expect(await screen.findByText("a · down")).toBeInTheDocument();
  expect(screen.getByText("a · up")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Diagnostics" })).toHaveAttribute(
    "href",
    `/v1/sessions/${session.id}/diagnostics`,
  );

  await user.click(screen.getByRole("button", { name: "Replay input" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      `/v1/sessions/${session.id}/replay`,
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(screen.getByRole("button", { name: "Replaying…" })).toBeDisabled();
});

test("walks event cursors and keeps the newest bounded timeline", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://simulator.test");
    const after = Number(url.searchParams.get("after"));
    const events =
      after === 0
        ? Array.from({ length: 500 }, (_, index) => ({
            sequence: index + 1,
            generation: 1,
            offset_ms: index,
            category: "peripheral",
            type: "peripheral.spi.transaction",
            source: "worker",
            data: { detail: `transaction ${index + 1}` },
          }))
        : after === 500
          ? [
              {
                sequence: 501,
                generation: 1,
                offset_ms: 501,
                category: "input",
                type: "input.key",
                source: "user",
                data: { key: "z", pressed: true },
              },
            ]
          : [];
    return new Response(
      JSON.stringify({
        session_id: session.id,
        generation: 1,
        events_dropped: 0,
        cursor_truncated: false,
        next_after: events.at(-1)?.sequence ?? after,
        events,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });
  vi.stubGlobal("fetch", fetchMock);

  render(<TimelineInspector session={session} />);

  expect(await screen.findByText("z · down")).toBeInTheDocument();
  expect(screen.getByText("200 visible")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    `/v1/sessions/${session.id}/events?after=500&limit=500`,
    undefined,
  );
});
