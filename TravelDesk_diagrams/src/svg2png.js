// Render a D2 SVG to PNG with the headless Chrome that ships with the Mermaid CLI (2x for crisp text).
const puppeteer = require("/opt/npm-tools/node_modules/puppeteer");
const fs = require("fs");
(async () => {
  const [inp, out] = process.argv.slice(2);
  const svg = fs.readFileSync(inp, "utf8");
  const m = svg.match(/viewBox="([\d.\- ]+)"/); const [, , w, h] = m[1].split(" ").map(Number);
  const browser = await puppeteer.launch({ executablePath: "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome", args: ["--no-sandbox", "--font-render-hinting=none"] });
  const page = await browser.newPage();
  await page.setViewport({ width: Math.ceil(w), height: Math.ceil(h), deviceScaleFactor: 2 });
  await page.setContent('<html><body style="margin:0;background:#fff">' + svg.replace(/width="[^"]*"/, 'width="' + w + '"').replace(/height="[^"]*"/, 'height="' + h + '"') + "</body></html>");
  await page.screenshot({ path: out, clip: { x: 0, y: 0, width: Math.ceil(w), height: Math.ceil(h) } });
  await browser.close();
  console.log(out, Math.ceil(w), "x", Math.ceil(h), "px (1x)");
})();
