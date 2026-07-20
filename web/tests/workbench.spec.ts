// SPDX-License-Identifier: GPL-2.0-only

import { expect, test, type Page } from "@playwright/test";

const boardProfiles = [
  {
    id: "cardputer-adv",
    label: "Cardputer ADV compatible",
    mcu: "ESP32-S3FN8",
    flash_size_bytes: 8 * 1024 * 1024,
    psram_size_mib: 0,
    display: {
      controller: "ST7789",
      width: 240,
      height: 135,
      transport: "SPI",
      rotation_degrees: 90,
    },
    capabilities: [],
  },
  {
    id: "sticks3",
    label: "StickS3 compatible",
    mcu: "ESP32-S3-PICO-1-N8R8",
    flash_size_bytes: 8 * 1024 * 1024,
    psram_size_mib: 8,
    display: {
      controller: "ST7789",
      width: 135,
      height: 240,
      transport: "SPI",
      rotation_degrees: 0,
    },
    capabilities: [],
  },
];

const sessionId = "a".repeat(32);

const runningSession = {
  id: sessionId,
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

async function openWorkbench(page: Page): Promise<void> {
  await page.route("**/anonymous/config", (route) =>
    route.fulfill({ status: 404 }),
  );
  await page.route("**/v1/boards", (route) =>
    route.fulfill({ json: boardProfiles }),
  );
  await page.goto("/");
  await expect(page).toHaveTitle("ESP32-S3 Simulator");
}

test("validates a merged image and switches idle board profiles", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  await openWorkbench(page);

  const firmware = Buffer.alloc(4096);
  firmware.set([0xe9, 0x03, 0x02, 0x00]);
  await page.locator('input[type="file"]').setInputFiles({
    name: "firmware-merged.bin",
    mimeType: "application/octet-stream",
    buffer: firmware,
  });

  await expect(page.getByText("Merged image header")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start session" })).toBeEnabled();
  await page.getByRole("button", { name: "StickS3" }).click();
  await expect(
    page.getByLabel("StickS3 compatible 135 by 240 framebuffer"),
  ).toBeVisible();
});

test("keeps account saves explicit and runs them in a fresh session", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  const savedId = "b".repeat(32);
  const savedApp = {
    id: savedId,
    name: "Cardputer Chess",
    board_id: "cardputer-adv",
    source_size_bytes: 4096,
    created_at: "2026-07-19T00:00:00Z",
    updated_at: "2026-07-19T00:00:00Z",
  };
  await page.route("**/anonymous/config", (route) =>
    route.fulfill({
      json: {
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
      },
    }),
  );
  await page.route("**/v1/boards", (route) =>
    route.fulfill({ json: boardProfiles }),
  );
  await page.route("**/v1/saved-apps", (route) =>
    route.fulfill({ json: { apps: [savedApp], limit: 10 } }),
  );
  let replacementReceived = false;
  await page.route(`**/v1/saved-apps/${savedId}?*`, async (route) => {
    replacementReceived = route.request().method() === "PUT";
    await route.fulfill({ json: { ...savedApp, source_size_bytes: 8192 } });
  });
  await page.route(`**/v1/saved-apps/${savedId}/sessions`, (route) =>
    route.fulfill({ status: 201, json: runningSession }),
  );
  await page.route(`**/v1/sessions/${sessionId}`, (route) =>
    route.fulfill({ json: runningSession }),
  );
  await page.goto("/");

  await expect(page.getByText("Saved apps", { exact: true })).toBeVisible();
  await expect(page.getByText("Cardputer Chess")).toBeVisible();
  await expect(page.getByText("Normal sessions stay unsaved.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save selected" })).toBeDisabled();

  const firmware = Buffer.alloc(8192);
  firmware.set([0xe9, 0x03, 0x02, 0x00]);
  await page.locator('input[type="file"]').setInputFiles({
    name: "chess-merged.bin",
    mimeType: "application/octet-stream",
    buffer: firmware,
  });
  await expect(page.getByRole("button", { name: "Save selected" })).toBeEnabled();
  if (process.env.SIMULATOR_CAPTURE_DIR) {
    await page.screenshot({
      path: `${process.env.SIMULATOR_CAPTURE_DIR}/saved-apps-desktop.png`,
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: /Firmware setup/ }).click();
    const savedCard = page.getByText("Cardputer Chess").locator("..").locator("..");
    const setupRegion = page.locator(".setup-region");
    const [savedCardBox, setupRegionBox] = await Promise.all([
      savedCard.boundingBox(),
      setupRegion.boundingBox(),
    ]);
    expect(savedCardBox).not.toBeNull();
    expect(setupRegionBox).not.toBeNull();
    expect((savedCardBox?.y ?? 0) + (savedCardBox?.height ?? 0)).toBeLessThanOrEqual(
      (setupRegionBox?.y ?? 0) + (setupRegionBox?.height ?? 0),
    );
    await page.screenshot({
      path: `${process.env.SIMULATOR_CAPTURE_DIR}/saved-apps-mobile.png`,
      fullPage: true,
    });
    await page.setViewportSize({ width: 1536, height: 1024 });
  }
  await page
    .getByRole("button", { name: "Replace Cardputer Chess with selected firmware" })
    .click();
  await expect(page.getByText("Replace with selected Cardputer ADV image?")).toBeVisible();
  await page.getByRole("group", { name: "Replace Cardputer Chess" }).getByText("Confirm").click();
  await expect.poll(() => replacementReceived).toBe(true);

  await page.getByRole("button", { name: "Run Cardputer Chess" }).click();
  await expect(page.getByText("Running")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save selected" })).toBeDisabled();
});

test("exchanges a shared Supabase identity before opening account storage", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const now = Math.floor(Date.now() / 1000);
  const userId = "11111111-2222-4333-8444-555555555555";
  const tokenPayload = Buffer.from(
    JSON.stringify({
      aud: "authenticated",
      exp: now + 3600,
      session_id: "66666666-7777-4888-8999-aaaaaaaaaaaa",
      sub: userId,
    }),
  ).toString("base64url");
  const accessToken = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.${tokenPayload}.playwright`;
  let gatewayAuthorized = false;

  await page.route("**/anonymous/config", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        anonymous_enabled: true,
        auth_mode: "supabase",
        supabase_url: "https://identity.example.test",
        supabase_publishable_key: "sb_publishable_playwright_public_key",
        authorized: gatewayAuthorized,
        access_kind: gatewayAuthorized ? "account" : null,
        capability: false,
        site_key: "0x4AAAAA-browser-site-key",
        action: "anonymous_session",
        heartbeat_interval_seconds: 15,
        session_lifetime_seconds: 180,
        saved_apps_enabled: gatewayAuthorized,
        saved_app_limit: gatewayAuthorized ? 10 : null,
      },
    }),
  );
  await page.route("https://identity.example.test/**", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({
        status: 204,
        headers: {
          "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
          "Access-Control-Allow-Methods": "POST",
          "Access-Control-Allow-Origin": "http://127.0.0.1:4174",
        },
      });
      return;
    }
    expect(route.request().url()).toContain("/auth/v1/token?grant_type=password");
    expect(await route.request().postDataJSON()).toMatchObject({
      email: "owner@example.com",
      password: "playwright-only-password",
    });
    await route.fulfill({
      headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:4174" },
      json: {
        access_token: accessToken,
        expires_at: now + 3600,
        expires_in: 3600,
        refresh_token: "playwright-refresh-token",
        token_type: "bearer",
        user: {
          app_metadata: { provider: "email", providers: ["email"] },
          aud: "authenticated",
          created_at: "2026-07-19T00:00:00Z",
          email: "owner@example.com",
          id: userId,
          identities: [],
          role: "authenticated",
          updated_at: "2026-07-19T00:00:00Z",
          user_metadata: {},
        },
      },
    });
  });
  await page.route("**/auth/exchange", async (route) => {
    expect(route.request().headers().authorization).toBe(`Bearer ${accessToken}`);
    gatewayAuthorized = true;
    await route.fulfill({
      json: {
        authenticated: true,
        auth_provider: "supabase",
        username: "owner@example.com",
        expires_at: now + 3600,
      },
    });
  });
  await page.route("**/v1/saved-apps", (route) =>
    route.fulfill({ json: { apps: [], limit: 10 } }),
  );
  await page.route("**/v1/boards", (route) =>
    route.fulfill({ json: boardProfiles }),
  );
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Sign in with your Zillion account" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue with one unsaved anonymous run" }),
  ).toBeVisible();
  if (process.env.SIMULATOR_CAPTURE_DIR) {
    await page.screenshot({
      path: `${process.env.SIMULATOR_CAPTURE_DIR}/account-gate-desktop.png`,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: `${process.env.SIMULATOR_CAPTURE_DIR}/account-gate-mobile.png`,
    });
    await page.setViewportSize({ width: 1280, height: 900 });
  }
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Password").fill("playwright-only-password");
  await page.getByRole("button", { name: "Sign in and open workbench" }).click();

  await expect(
    page.getByRole("heading", { name: "Sign in with your Zillion account" }),
  ).toBeHidden();
  await expect(page.getByText("Saved apps", { exact: true })).toBeVisible();
  await expect(page.getByText("No saved apps yet. Saving is always explicit.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});

test("keeps portrait device and serial panels within the viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 1536 });
  await openWorkbench(page);

  await expect(page.getByLabel("Virtual device stage")).toBeVisible();
  const status = await page.locator(".status-bar").boundingBox();
  expect(status).not.toBeNull();
  expect(Math.round((status?.y ?? 0) + (status?.height ?? 0))).toBe(1536);

  await page.getByRole("button", { name: "Serial" }).click();
  await expect(page.getByRole("region", { name: "Serial console" })).toBeVisible();
  await expect(page.getByLabel("Virtual device stage")).toBeHidden();
});

test("shows recorded input, diagnostics, and replay in the inspector", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1536, height: 1024 });
  await page.route("**/v1/sessions", (route) =>
    route.fulfill({ status: 201, json: runningSession }),
  );
  await page.route(`**/v1/sessions/${sessionId}`, (route) =>
    route.fulfill({ json: runningSession }),
  );
  await page.route(`**/v1/sessions/${sessionId}/events?*`, (route) =>
    route.fulfill({
      json: {
        session_id: sessionId,
        generation: 1,
        events_dropped: 0,
        cursor_truncated: false,
        next_after: 2,
        events: [
          {
            sequence: 1,
            generation: 1,
            offset_ms: 300,
            category: "input",
            type: "input.key",
            source: "user",
            data: { key: "enter", pressed: true },
          },
          {
            sequence: 2,
            generation: 1,
            offset_ms: 340,
            category: "input",
            type: "input.key",
            source: "user",
            data: { key: "enter", pressed: false },
          },
        ],
      },
    }),
  );
  await page.route(`**/v1/sessions/${sessionId}/replay`, (route) =>
    route.fulfill({
      status: 202,
      json: {
        session_id: sessionId,
        generation: 1,
        status: "queued",
        speed: 1,
        error: null,
        action_count: 2,
        actions_dropped: 0,
      },
    }),
  );
  await openWorkbench(page);

  const firmware = Buffer.alloc(4096);
  firmware.set([0xe9, 0x03, 0x02, 0x00]);
  await page.locator('input[type="file"]').setInputFiles({
    name: "firmware-merged.bin",
    mimeType: "application/octet-stream",
    buffer: firmware,
  });
  await page.getByRole("button", { name: "Start session" }).click();
  await page.getByRole("tab", { name: "Timeline" }).click();

  await expect(page.getByText("enter · down")).toBeVisible();
  await expect(page.getByRole("link", { name: "Diagnostics" })).toHaveAttribute(
    "href",
    `/v1/sessions/${sessionId}/diagnostics`,
  );
  await page.getByRole("button", { name: "Replay input" }).click();
  await expect(page.getByRole("button", { name: "Replaying…" })).toBeDisabled();
});

test("keeps hosted workbench locked until anonymous verification succeeds", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addInitScript(() => {
    const hosted = globalThis as unknown as {
      __turnstileCallback?: (token: string) => void;
      turnstile?: {
        render: (
          _container: unknown,
          options: { callback: (token: string) => void },
        ) => string;
        reset: () => void;
        remove: () => void;
      };
    };
    hosted.turnstile = {
      render: (_container, options) => {
        hosted.__turnstileCallback = options.callback;
        return "playwright-widget";
      },
      reset: () => undefined,
      remove: () => undefined,
    };
  });
  await page.route("**/anonymous/config", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        authorized: false,
        access_kind: null,
        capability: false,
        site_key: "0x4AAAAA-browser-site-key",
        action: "anonymous_session",
        heartbeat_interval_seconds: 15,
        session_lifetime_seconds: 180,
      },
    }),
  );
  await page.route("**/anonymous/capabilities", async (route) => {
    expect((await route.request().postDataJSON()).token).toBe("playwright-token");
    await route.fulfill({ status: 201, json: { anonymous: true, expires_at: 1234 } });
  });
  await page.route("**/v1/boards", (route) => route.fulfill({ json: boardProfiles }));
  await page.goto("/");

  const gate = page.getByRole("heading", {
    name: "Verify to start a temporary simulator",
  });
  await expect(gate).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const panelBox = await page.locator(".access-gate-panel").boundingBox();
  expect(panelBox).not.toBeNull();
  expect((panelBox?.x ?? 0) + (panelBox?.width ?? 0)).toBeLessThanOrEqual(390);
  expect((panelBox?.y ?? 0) + (panelBox?.height ?? 0)).toBeLessThanOrEqual(844);
  await page.evaluate(() => {
    const hosted = globalThis as unknown as {
      __turnstileCallback?: (token: string) => void;
    };
    hosted.__turnstileCallback?.("playwright-token");
  });
  await expect(gate).toBeHidden();
  await expect(page.getByRole("button", { name: /Firmware setup/ })).toBeVisible();
});
