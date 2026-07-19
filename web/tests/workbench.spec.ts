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
