// SPDX-License-Identifier: GPL-2.0-only

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  delete window.turnstile;
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the real setup workflow and changes idle device profile", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/anonymous/config")) return Promise.resolve(new Response(null, { status: 404 }));
      return Promise.resolve(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }));
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByText("ESP32-S3 Simulator")).toBeInTheDocument();
    expect(screen.getByText("Drop merged firmware.bin")).toBeInTheDocument();
    expect(screen.getByLabelText("Cardputer ADV compatible 240 by 135 framebuffer"))
      .toBeInTheDocument();
    expect(screen.getByText("Keyboard matrix")).toBeInTheDocument();
    expect(screen.getByText("BMI270 motion")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Power" }));

    expect(screen.getByText("ADC battery state")).toBeInTheDocument();
    expect(screen.queryByText("Charging")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Timeline" }));
    expect(screen.getByText("No session timeline")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "StickS3" }));

    expect(screen.getByLabelText("StickS3 compatible 135 by 240 framebuffer"))
      .toBeInTheDocument();
    expect(screen.getByText("ESP32-S3-PICO-1-N8R8")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Power" }));
    expect(screen.getByText("M5PM1 behavioral state")).toBeInTheDocument();
    expect(screen.getByText("Charging")).toBeInTheDocument();
  });

  it("fails closed behind hosted verification and unlocks with an HttpOnly capability", async () => {
    let challengeCallback: ((token: string) => void) | null = null;
    window.turnstile = {
      render: vi.fn((_container, options) => {
        challengeCallback = options.callback;
        return "widget-1";
      }),
      reset: vi.fn(),
      remove: vi.fn(),
    };
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/anonymous/config")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              authorized: false,
              access_kind: null,
              capability: false,
              site_key: "0x4AAAAA-browser-site-key",
              action: "anonymous_session",
              heartbeat_interval_seconds: 15,
              session_lifetime_seconds: 180,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      if (url.includes("/anonymous/capabilities")) {
        return Promise.resolve(
          new Response(JSON.stringify({ anonymous: true, expires_at: 1234 }), {
            status: 201,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Verify to start a temporary simulator",
      }),
    ).toBeInTheDocument();
    await waitFor(() => expect(challengeCallback).not.toBeNull());
    await act(async () => challengeCallback?.("verified-browser-token"));
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", {
          name: "Verify to start a temporary simulator",
        }),
      ).not.toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/anonymous/capabilities",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ token: "verified-browser-token" }),
      }),
    );
    expect(screen.queryByText("Saved apps")).not.toBeInTheDocument();
  });

  it("shows encrypted saved slots only for an account and keeps saving explicit", async () => {
    const firstSaved = {
      id: "b".repeat(32),
      name: "Cardputer Chess",
      board_id: "cardputer-adv",
      source_size_bytes: 4096,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    };
    const fetchMock = vi.fn().mockImplementation(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/anonymous/config")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                enabled: false,
                authorized: true,
                access_kind: "account",
                capability: false,
                site_key: null,
                action: null,
                heartbeat_interval_seconds: null,
                session_lifetime_seconds: null,
                saved_apps_enabled: true,
                saved_app_limit: 10,
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        if (url.includes("/v1/saved-apps") && (!init?.method || init.method === "GET")) {
          return Promise.resolve(
            new Response(JSON.stringify({ apps: [firstSaved], limit: 10 }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        if (url.includes("/v1/saved-apps") && init?.method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                ...firstSaved,
                id: "c".repeat(32),
                name: "Tournament build",
              }),
              {
                status: 201,
                headers: { "Content-Type": "application/json" },
              },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Saved apps")).toBeInTheDocument();
    expect(await screen.findByText("Cardputer Chess")).toBeInTheDocument();
    expect(screen.getByText("1/10")).toBeInTheDocument();
    expect(screen.getByText(/Normal sessions stay unsaved\./)).toBeInTheDocument();

    const image = new Uint8Array(4096);
    image.set([0xe9, 0x03, 0x02, 0x00]);
    await user.upload(
      screen.getByLabelText(/Drop merged firmware\.bin/),
      new File([image], "account-chess.bin", { type: "application/octet-stream" }),
    );
    const name = screen.getByLabelText("App name");
    await user.clear(name);
    await user.type(name, "Tournament build");
    await user.click(screen.getByRole("button", { name: "Save selected" }));

    await waitFor(() => expect(screen.getByText("2/10")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/saved-apps?name=Tournament+build&board_id=cardputer-adv",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
      }),
    );
  });

  it("lists a curated Cardputer Chess demo and launches it without a browser upload", async () => {
    const fetchMock = vi.fn().mockImplementation(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/anonymous/config")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                enabled: true,
                authorized: true,
                access_kind: "account",
                capability: false,
                site_key: null,
                action: null,
                heartbeat_interval_seconds: null,
                session_lifetime_seconds: null,
                demo_apps_enabled: true,
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        if (url.endsWith("/v1/demos") && (!init?.method || init.method === "GET")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                demos: [
                  {
                    id: "cardputer-chess",
                    name: "Cardputer Chess",
                    description: "Complete offline chess on the Cardputer ADV profile.",
                    board_id: "cardputer-adv",
                    source_size_bytes: 687072,
                    firmware_sha256: "a".repeat(64),
                    source_url: "https://github.com/SimonBear03/cardputer-chess",
                    license: "MIT",
                    license_url:
                      "https://github.com/SimonBear03/cardputer-chess/blob/main/LICENSE",
                    notices_url:
                      "https://github.com/SimonBear03/cardputer-chess/blob/main/THIRD_PARTY.md",
                  },
                ],
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        if (url.includes("/v1/demos/cardputer-chess/sessions") && init?.method === "POST") {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: "a".repeat(32),
                board_id: "cardputer-adv",
                state: "running",
                created_at: "2026-07-21T00:00:00Z",
                expires_at: "2026-07-21T00:02:00Z",
                exit_code: null,
                generation: 1,
                firmware: {
                  source_size_bytes: 687072,
                  flash_size_bytes: 8388608,
                  source_sha256: "a".repeat(64),
                  flash_sha256: "b".repeat(64),
                  segment_count: 4,
                  flash_mode: 2,
                },
                recording: {
                  event_count: 0,
                  events_dropped: 0,
                  replayable_action_count: 0,
                  replayable_actions_dropped: 0,
                  trace_events_recorded: 0,
                  trace_events_dropped: 0,
                },
                replay: { status: "idle", speed: null, error: null },
              }),
              { status: 201, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Try a demo")).toBeInTheDocument();
    expect(await screen.findByText("Cardputer Chess")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /MIT/ })).toHaveAttribute(
      "href",
      "https://github.com/SimonBear03/cardputer-chess/blob/main/LICENSE",
    );

    await user.click(screen.getByRole("button", { name: "Run demo" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/v1/demos/cardputer-chess/sessions",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(screen.getByText("Running")).toBeInTheDocument();
  });
});
