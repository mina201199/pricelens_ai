import { expect, test } from "@playwright/test";

test("home radar and cabbage detail preserve wholesale semantics", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: /現在買/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "今日價格雷達" })).toBeVisible();
  await expect(page.getByText("本週漲價榜")).toBeVisible();

  const cabbage = page.getByRole("link", { name: /高麗菜/ }).first();
  await expect(cabbage).toBeVisible();
  await cabbage.click();

  await expect(page.getByRole("heading", { name: "高麗菜" })).toBeVisible();
  await expect(page.getByText("這不是零售售價。")).toBeVisible();
  await expect(page.getByText("新台幣／公斤（批發）")).toBeVisible();
  await expect(page.getByLabel("批發均價與交易量走勢圖")).toBeVisible();
  await expect(page.locator(".recharts-surface")).toBeVisible();
  expect(pageErrors).toEqual([]);
});

test("controlled AI search returns sourced wholesale facts", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByLabel("輸入價格問題").fill("高麗菜現在算貴嗎？");
  await page.getByRole("button", { name: "送出問題" }).click();

  await expect(page.getByText(/高麗菜.*35\.1106.*偏高/)).toBeVisible();
  await expect(page.getByText("資料 2026-09-24")).toBeVisible();
  await expect(page.getByText("批發 · 元／公斤")).toBeVisible();
  await expect(page.getByRole("link", { name: "農業部農糧署" })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
