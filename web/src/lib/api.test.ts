// SPDX-License-Identifier: GPL-2.0-only

import { afterEach, vi } from "vitest";

import { controlSession, createSession } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("session power controls", () => {
  it("sends an explicit cold-power action through the bounded control route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ state: "powered_off" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await controlSession("a".repeat(32), "power-off");

    expect(fetchMock).toHaveBeenCalledWith(
      `/v1/sessions/${"a".repeat(32)}/control`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ action: "power-off" }),
      }),
    );
  });
});

describe("session upload privacy", () => {
  it("sends only the board and merged image in multipart session creation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "a".repeat(32),
          board_id: "cardputer-adv",
          state: "running",
          created_at: "2026-07-20T00:00:00Z",
          expires_at: "2026-07-20T00:02:00Z",
          exit_code: null,
          firmware: {},
          generation: 1,
          recording: {},
          replay: {},
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const firmware = new File([new Uint8Array([0xe9, 1, 0, 0])], "firmware.bin");

    await createSession("cardputer-adv", firmware);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    const body = init.body as FormData;
    expect([...body.keys()]).toEqual(["board_id", "firmware"]);
    expect(body.get("firmware")).toBeInstanceOf(File);
    expect(body.get("firmware")).toMatchObject({
      name: "firmware.bin",
      size: firmware.size,
    });
    expect(body.has("symbols")).toBe(false);
    expect(body.has("elf")).toBe(false);
  });
});
