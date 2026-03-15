const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  await page.goto('http://localhost:3000/collection', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: '/Users/hs/.gemini/antigravity/brain/de69c7c8-02d5-42fb-8179-2d44085942f6/collection_filtered.png' });
  
  await page.goto('http://localhost:3000/offers', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: '/Users/hs/.gemini/antigravity/brain/de69c7c8-02d5-42fb-8179-2d44085942f6/offers_sorted.png' });
  
  await browser.close();
})();
