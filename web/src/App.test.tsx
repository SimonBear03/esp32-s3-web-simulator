// SPDX-License-Identifier: GPL-2.0-only

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the real setup workflow and changes idle device profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
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

    await user.click(screen.getByRole("button", { name: "StickS3" }));

    expect(screen.getByLabelText("StickS3 compatible 135 by 240 framebuffer"))
      .toBeInTheDocument();
    expect(screen.getByText("ESP32-S3-PICO-1-N8R8")).toBeInTheDocument();
    expect(screen.getByText("M5PM1 behavioral state")).toBeInTheDocument();
    expect(screen.getByText("Charging")).toBeInTheDocument();
  });
});
