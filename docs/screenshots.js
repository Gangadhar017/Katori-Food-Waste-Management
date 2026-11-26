// Walks the running app and saves the README screenshots.
//   node docs/screenshots.js [base url] [output folder]
// Needs Playwright (npm i playwright), or PLAYWRIGHT_MODULE pointing at an existing install.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");

const base = process.argv[2] || "http://127.0.0.1:8000";
const out = process.argv[3] || "docs/screenshots";

async function enter(page, role) {
  await page.goto(`${base}/#/`);
  await page.getByRole("button", { name: new RegExp(role) }).click();
  await page.waitForURL(/#\/(home|kitchen|manage)/);
  await page.waitForLoadState("networkidle").catch(() => {});
}

(async () => {
  const browser = await chromium.launch();
  const desktop = await browser.newContext({ viewport: { width: 1360, height: 860 }, deviceScaleFactor: 1.5, colorScheme: "light" });
  const page = await desktop.newPage();
  const shot = async (name, options = {}) => {
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${out}/${name}.png`, ...options });
    console.log("saved", name);
  };

  await page.goto(`${base}/#/`);
  await page.getByText("Sittings logged").waitFor();
  await shot("landing");

  await enter(page, "The mess manager");
  await page.getByText("Waste by week").waitFor();
  await shot("overview");
  await page.getByText("Waste by week").scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 420);
  await page.mouse.move(900, 330);
  await shot("waste-by-week");
  await page.goto(`${base}/#/manage/forecast`);
  await page.getByText("The week ahead").waitFor();
  await page.mouse.move(820, 430);
  await shot("forecast");
  await page.goto(`${base}/#/manage/waste`);
  await page.getByText("Waste per plate, by sitting").waitFor();
  await shot("waste");
  await page.mouse.wheel(0, 900);
  await shot("waste-heatmap");
  await page.goto(`${base}/#/manage/chart`);
  await page.getByText("Swaps worth making").waitFor();
  await page.mouse.wheel(0, 430);
  await shot("food-chart");
  await page.goto(`${base}/#/manage/models`);
  await page.getByText("Training runs").waitFor();
  await shot("models");
  await page.goto(`${base}/#/kitchen`);
  await page.getByText("Quantities").waitFor();
  await shot("cook-sheet");
  await page.goto(`${base}/#/kitchen/log`);
  await page.getByText("Pots").first().waitFor();
  await shot("weigh-in");
  await page.goto(`${base}/#/board/nilgiri`);
  await page.getByText("Now serving").waitFor();
  await shot("wall-display");
  await desktop.close();

  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, colorScheme: "light" });
  const mobile = await phone.newPage();
  const snap = async (name) => {
    await mobile.waitForTimeout(900);
    await mobile.screenshot({ path: `${out}/${name}.png` });
    console.log("saved", name);
  };
  await enter(mobile, "A resident");
  await mobile.getByText("Today").first().waitFor();
  await snap("resident-today");
  await mobile.goto(`${base}/#/line`);
  await mobile.getByRole("button", { name: "Take a token" }).click();
  await mobile.getByText("ahead of you").or(mobile.getByText("You are next")).or(mobile.getByText("Your turn")).first().waitFor();
  await snap("resident-token");
  await mobile.goto(`${base}/#/play/just-enough`);
  await mobile.getByRole("button", { name: "Start" }).click();
  const pourButton = mobile.getByRole("button", { name: "Hold to pour" });
  const box = await pourButton.boundingBox();
  await mobile.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await mobile.mouse.down();
  await mobile.waitForTimeout(1250);
  await mobile.screenshot({ path: `${out}/game-just-enough.png` });
  await mobile.mouse.up();
  await mobile.getByText("g poured").waitFor({ timeout: 4000 });
  console.log("saved game-just-enough; pour by pointer works:", await mobile.getByText("g poured").innerText());
  await mobile.goto(`${base}/#/ranks`);
  await mobile.getByText("Hostel board").waitFor();
  await snap("resident-board");
  await phone.close();
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
