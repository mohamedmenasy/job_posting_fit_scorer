import { expect, test } from "@playwright/test";

import { demoData } from "./fixtures";

// Definition of done (brief §52): profile → paste job → evaluate → detail with blockers and evidence → dashboard.
test("paste a job and see it blocked with evidence", async ({ page }) => {
  const demo = demoData();
  const posting = demo.postings["clearance_required"]!;

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Start with your profile" })).toBeVisible();

  await page.getByRole("link", { name: "Create profile" }).click();
  await page.locator("#resume").fill(demo.resume);
  await page.getByRole("radiogroup", { name: "Can you meet a security clearance requirement?" }).getByRole("radio", { name: "No", exact: true }).click();
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText(/Profile saved/)).toBeVisible();

  await page.keyboard.press("Escape");
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("n");
  await expect(page).toHaveURL(/\/jobs\/new$/);
  await page.locator("#description").fill(posting.description);
  await page.locator("#company").fill(posting.company);
  await page.locator("#title").fill(posting.title);
  await page.locator("#location").fill(posting.location);
  await page.getByRole("button", { name: "Save and evaluate" }).click();

  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name: posting.title })).toBeVisible();
  const blockers = page.locator("#blockers");
  await expect(blockers.getByText("Explicit security clearance requirement you cannot meet")).toBeVisible({ timeout: 15_000 });
  await expect(blockers.getByText(/Active Secret clearance required/)).toBeVisible();
  await expect(page.locator("header").getByText("Blocked", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  const row = page.getByRole("row", { name: new RegExp(posting.company) });
  await expect(row.getByText("Blocked", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Blocked/ })).toContainText("1");

  await page.keyboard.press("/");
  await expect(page.locator("#job-search")).toBeFocused();
});
