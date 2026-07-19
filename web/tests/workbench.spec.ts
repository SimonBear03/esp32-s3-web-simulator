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
