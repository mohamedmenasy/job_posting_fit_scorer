import path from "node:path";

import { expect, test } from "@playwright/test";

import { demoData } from "./fixtures";

const OUT = path.join(__dirname, "../../docs/screenshots");

test("capture README screenshots @screenshots", async ({ page, request }) => {
  const demo = demoData();
  const meta = await (await request.get("/api/meta")).json();
  await request.put("/api/profile", {
    data: {
      resume_text: demo.resume,
      preferences: demo.preferences,
      blocker_facts: { needs_visa_sponsorship: true, can_meet_clearance_requirement: false },
      tracked_skills: meta.default_tracked_skills,
    },
  });
  const jobs = Object.entries(demo.postings).map(([name, posting]) => ({ ...posting, external_id: `fixture:${name}`, source: "company_site" }));
  await request.post("/api/jobs/batch", { data: { jobs, auto_evaluate: true } });

  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.getByRole("row")).toHaveCount(9, { timeout: 15_000 });
  await page.screenshot({ path: `${OUT}/dashboard.png` });

  await page.getByRole("row", { name: /Ledgerly/ }).click();
  await expect(page.locator("#fit")).toBeVisible();
  await page.screenshot({ path: `${OUT}/job-detail.png`, fullPage: true });

  await page.goto("/");
  await page.getByRole("row", { name: /Aegis Mobile Systems/ }).click();
  await expect(page.locator("#blockers")).toBeVisible();
  await page.screenshot({ path: `${OUT}/job-blocked.png` });

  await page.goto("/profile");
  await expect(page.locator("#resume")).not.toBeEmpty();
  await page.screenshot({ path: `${OUT}/profile.png` });

  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/settings");
  await expect(page.getByLabel("Strong match from")).toBeVisible();
  await page.screenshot({ path: `${OUT}/scoring-dark.png` });
});
