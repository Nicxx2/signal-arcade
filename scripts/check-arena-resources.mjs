// Run against an isolated app/fixture with a stable Champion skill, never a production session.
// Usage: node scripts/check-arena-resources.mjs http://127.0.0.1:8875/
// Requires an installed Playwright runtime; PLAYWRIGHT_MODULE can name its absolute module path.
import { createRequire } from "node:module";
import assert from "node:assert/strict";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const target = process.argv[2];
if (!target || !/^https?:\/\//.test(target)) throw new Error("Supply the URL of an isolated, stable test fixture.");
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  await page.addInitScript(() => localStorage.setItem("signal-arcade-learning-ui-v1", JSON.stringify({ version: 2, activeView: "challenger", expandedSections: [], seenMilestoneIds: [], initialized: true })));
  page.on("request", (request) => assert.equal(request.method(), "GET", "Spectator interaction must never send a write request"));
  await page.goto(target);
  await page.getByRole("button", { name: "Learning", exact: true }).click();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  const samples = [];
  for (let cycle = 1; cycle <= 200; cycle++) {
    await page.locator(".ca-skill-launch").first().click();
    await page.locator('.ca-stage[data-renderer="3d"]').waitFor();
    const scene = await page.locator(".ca-stage").evaluate((element) => ({ ...element.dataset }));
    assert.ok(Number(scene.drawCalls) <= 80 && Number(scene.triangles) <= 50_000);
    assert.equal(Number(scene.textures), 0, "The texture-free scene must not reintroduce a shared PBR lookup texture");
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("[data-champion-renderer]").count(), 0);
    if ([20, 60, 100, 200].includes(cycle)) {
      await page.waitForTimeout(500);
      await cdp.send("HeapProfiler.collectGarbage");
      const { metrics } = await cdp.send("Performance.getMetrics");
      const sample = { cycle, ...Object.fromEntries(metrics.filter((item) => ["Nodes", "JSEventListeners", "JSHeapUsedSize"].includes(item.name)).map((item) => [item.name, item.value])) };
      samples.push(sample);
      console.log(JSON.stringify(sample));
    }
  }
  assert.ok(samples.at(-1).Nodes <= samples[0].Nodes + 8, "Detached nodes grew after warm-up; inspect a heap snapshot before release");
  assert.ok(samples.at(-1).JSEventListeners <= samples[0].JSEventListeners + 2, "Listeners accumulated across reopenings");
  console.log("Champion Arena resource regression passed.");
} finally {
  // Some Windows browser channels close their processes but leave the driver waiting on a pipe.
  await Promise.race([browser.close(), new Promise((resolve) => setTimeout(resolve, 5_000))]);
}
process.exit(0);
