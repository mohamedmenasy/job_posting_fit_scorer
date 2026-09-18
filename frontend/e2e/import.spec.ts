import path from "node:path";

import { expect, test } from "@playwright/test";

import { demoData } from "./fixtures";

const CSV = path.join(__dirname, "fixtures", "jobs.csv");

test("import a CSV, finish the draft, and evaluate it", async ({ page }) => {
  const demo = demoData();

  await page.goto("/profile");
  await page.locator("#resume").fill(demo.resume);
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText(/Profile saved/)).toBeVisible();

  await page.goto("/jobs/new");
  await page.getByRole("tab", { name: "From CSV" }).click();
  await page.locator("#csv-file").setInputFiles(CSV);
  await expect(page.getByText("Check the columns")).toBeVisible();

  // The "Notes" column has no obvious target, so it must default to being skipped.
  await expect(page.getByLabel("Notes", { exact: true })).toContainText("Skip this column");
  // Map it by hand to prove the mapping step is editable.
  await page.getByLabel("Notes", { exact: true }).click();
  await page.getByRole("option", { name: "External ID" }).click();

  await page.getByRole("button", { name: /Import 2 rows/ }).click();
  const summary = page.getByRole("status");
  await expect(summary).toContainText("Imported");
  await expect(summary.getByText("Jobs added")).toBeVisible();

  await page.getByRole("link", { name: /Finish 1 drafts/ }).click();
  const draftRow = page.getByRole("row", { name: /Parcelio/ });
  await expect(draftRow.getByText("Needs description")).toBeVisible();
  await draftRow.click();

  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Evaluate" })).toBeDisabled();
  await page.locator("#draft-description").fill(demo.postings["flutter_heavy"]!.description);
  await page.getByRole("button", { name: /Save and unlock evaluation/ }).click();
  await expect(page.getByText("Job saved")).toBeVisible();

  await page.getByRole("button", { name: "Evaluate" }).click();
  await expect(page.locator("#fit")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("header").getByText(/match|Review|Blocked/)).toBeVisible();
});
