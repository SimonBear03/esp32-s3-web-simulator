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
  });
});
