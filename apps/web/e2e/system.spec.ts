import { expect, test } from "@playwright/test";

test("shows a guest-first startup boundary", async ({ page }) => {
  await page.goto("/");

  await expect(
    page
      .getByRole("heading", { name: "Create your first workspace" })
      .or(page.getByRole("heading", { name: "Authentication needs configuration" })),
  ).toBeVisible();
  await expect(page.getByLabel("Email address")).toHaveCount(0);
});

test("guest-first startup remains usable on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await expect(
    page
      .getByRole("heading", { name: "Create your first workspace" })
      .or(page.getByRole("heading", { name: "Authentication needs configuration" })),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Send sign-in link" })).toHaveCount(0);
});
