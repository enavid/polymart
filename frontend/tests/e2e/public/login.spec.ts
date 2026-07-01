import { expect, test } from "@playwright/test";

const USER = {
  id: 1,
  phone_number: "+989123456789",
  email: "",
  full_name: "Ali",
  is_staff: false,
};

// Full login flow in a real browser. The backend is intercepted at the network
// layer so the test exercises the whole UI path (render → submit → redirect →
// authenticated account view) without needing the live API.
test("a user can log in and land on their account page", async ({ page }) => {
  let loggedIn = false;

  await page.route("**/api/v1/auth/me/", async (route) => {
    if (loggedIn) {
      await route.fulfill({ status: 200, json: USER });
    } else {
      await route.fulfill({ status: 401, json: { detail: "no" } });
    }
  });

  await page.route("**/api/v1/auth/login/", async (route) => {
    loggedIn = true;
    await route.fulfill({ status: 200, json: USER });
  });

  await page.goto("/login");

  await page.getByLabel("شمارهٔ موبایل").fill("09123456789");
  await page.getByLabel("رمز عبور").fill("secret123");
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText("+989123456789")).toBeVisible();
});
