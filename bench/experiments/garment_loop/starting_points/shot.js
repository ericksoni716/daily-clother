// usage: node shot.js page.html out.png width [scale]
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: +process.argv[4], height: 800 }, deviceScaleFactor: +(process.argv[5] || 1) });
  await p.goto('file://' + process.argv[2]); await p.screenshot({ path: process.argv[3], fullPage: true }); await b.close();
})();
