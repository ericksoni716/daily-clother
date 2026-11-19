// Rasterise the app's SVG drawings through Chromium, as the app draws garments in a browser.
// usage: node shoot.js jobs.json   where jobs.json is [{"svg": "/path/a.svg", "png": "/path/a.png", "scale": 2}, ...]
// Each PNG keeps a transparent background (the drawing's card is taken out before it gets here).
const fs = require('fs');
const { chromium } = require('playwright');
(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch();
  const pages = {};
  for (const job of jobs) {
    const scale = job.scale || 2;
    if (!pages[scale]) pages[scale] = await browser.newPage({ viewport: { width: 400, height: 460 }, deviceScaleFactor: scale });
    const page = pages[scale];
    const svg = fs.readFileSync(job.svg, 'utf8');
    await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">${svg}</body></html>`);
    const el = await page.$('svg');
    await el.screenshot({ path: job.png, omitBackground: true });
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
