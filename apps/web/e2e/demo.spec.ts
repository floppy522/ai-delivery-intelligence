import { expect, test } from "@playwright/test";

test("demo review shows current state, temporal delta, evidence, policy, and history", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Analyze delivery" }).click();
  await expect(page.getByText("No previous snapshot available")).toBeVisible();
  await page.getByRole("button", { name: "Advance to T2" }).click();
  await expect(page.getByText("AT RISK").first()).toBeVisible();
  await expect(page.getByText("Blocker SLA exceeded")).toBeVisible();
  await page.getByText("Evidence & policy").first().click();
  await expect(page.getByText("blocker-policy.md#critical-blocker-sla").first()).toBeVisible();
  await expect(page.getByText("Current assessment")).toBeVisible();
  await expect(page.getByText("Current state only")).toBeVisible();
  await page.screenshot({ path: "test-results/main-screen.png", fullPage: true });
});
