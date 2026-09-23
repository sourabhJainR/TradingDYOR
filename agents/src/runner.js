import { chromium } from "playwright";
import { writeFile } from "node:fs/promises";

const args = process.argv.slice(2);
const url = args[args.indexOf("--url") + 1];
if (!url) {
  console.error("Usage: node src/runner.js --url <url>");
  process.exit(2);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  userAgent: "TradingDYOR/0.1 research collector; public-source research"
});

const started = Date.now();
await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});

const title = await page.title();
const text = await page.locator("body").innerText();
const links = await page.locator("a").evaluateAll(as =>
  as.slice(0, 100).map(a => ({text:(a.innerText||"").trim(), href:a.href}))
);

const result = {
  url,
  title,
  retrieved_at: new Date().toISOString(),
  extraction_method: "playwright",
  elapsed_ms: Date.now() - started,
  excerpt: text.replace(/\\s+/g, " ").slice(0, 12000),
  links
};

console.log(JSON.stringify(result, null, 2));
await writeFile("last-research.json", JSON.stringify(result, null, 2));
await browser.close();
