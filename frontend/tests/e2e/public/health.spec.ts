import { expect, test } from "@playwright/test";

test("home page renders the platform name and backend status", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Polymart" })).toBeVisible();
  await expect(page.getByTestId("backend-state")).toBeVisible();
});
