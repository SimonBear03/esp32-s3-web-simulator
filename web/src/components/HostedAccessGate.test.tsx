// SPDX-License-Identifier: GPL-2.0-only

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import type { HostedAccessController } from "../hooks/useHostedAccess";
import { HostedAccessGate } from "./HostedAccessGate";

function accountController(
  overrides: Partial<HostedAccessController> = {},
): HostedAccessController {
  return {
    state: "account",
    config: {
      enabled: true,
      anonymous_enabled: true,
      authorized: false,
      access_kind: null,
      capability: false,
      site_key: "0x4AAAAA-browser-site-key",
      action: "anonymous_session",
      heartbeat_interval_seconds: 15,
      session_lifetime_seconds: 180,
      auth_mode: "supabase",
      supabase_url: "https://project.supabase.co",
      supabase_publishable_key: "sb_publishable_test_key_12345",
    },
    error: null,
    submitting: false,
    retry: vi.fn(),
    signIn: vi.fn().mockResolvedValue(true),
    signOut: vi.fn().mockResolvedValue(undefined),
    useAccount: vi.fn(),
    useAnonymous: vi.fn(),
    verified: vi.fn(),
    ...overrides,
  };
}

describe("HostedAccessGate", () => {
  it("signs in through the shared Zillion Supabase identity flow", async () => {
    const access = accountController();
    const user = userEvent.setup();
    render(<HostedAccessGate access={access} />);

    expect(
      screen.getByRole("heading", { name: "Sign in with your Zillion account" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Simulator content stays on this VPS/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in and open workbench" }));

    expect(access.signIn).toHaveBeenCalledWith(
      "owner@example.com",
      "correct horse battery",
    );
    await waitFor(() => expect(screen.getByLabelText("Password")).toHaveValue(""));
  });

  it("keeps the explicit unsaved anonymous path available", async () => {
    const access = accountController();
    const user = userEvent.setup();
    render(<HostedAccessGate access={access} />);
    await user.click(
      screen.getByRole("button", { name: "Continue with one unsaved anonymous run" }),
    );
    expect(access.useAnonymous).toHaveBeenCalledOnce();
  });
});
