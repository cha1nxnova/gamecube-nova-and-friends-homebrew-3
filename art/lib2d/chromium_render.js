// Rasterise a list of SVG files to PNG in ONE headless Chromium session.
//
//   node chromium_render.js jobs.json
//
// jobs.json = [{"svg": "/abs/in.svg", "png": "/abs/out.png", "size": 192, "background": null}, ...]
// "size" is the output width and height in pixels; "background" is null for a transparent PNG or a CSS colour.
// A job may instead give "width" and "height" (used for contact sheets, which are not square).
// Needs Node with the `playwright` package resolvable (dev-time only; the app never runs this).
const fs = require('fs');
const path = require('path');

async function main() {
  const jobsFile = process.argv[2];
  if (!jobsFile) {
    console.error('usage: node chromium_render.js jobs.json');
    process.exit(2);
  }
  let chromium;
  try {
    ({ chromium } = require('playwright'));
  } catch (e) {
    console.error('playwright is not installed: ' + e.message);
    process.exit(3);
  }
  const jobs = JSON.parse(fs.readFileSync(jobsFile, 'utf8'));
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 512, height: 512 }, deviceScaleFactor: 1 });
    let w0 = 0, h0 = 0;
    for (const job of jobs) {
      const w = job.width || job.size;
      const h = job.height || job.size;
      if (w !== w0 || h !== h0) {
        await page.setViewportSize({ width: w, height: h });
        w0 = w; h0 = h;
      }
      const svg = fs.readFileSync(job.svg, 'utf8');
      const bg = job.background || 'transparent';
      const html = '<!doctype html><html><head><style>' +
        'html,body{margin:0;padding:0;background:' + bg + ';overflow:hidden}' +
        'svg{display:block;width:' + w + 'px;height:' + h + 'px}' +
        '</style></head><body>' + svg + '</body></html>';
      await page.setContent(html, { waitUntil: 'load' });
      fs.mkdirSync(path.dirname(job.png), { recursive: true });
      await page.screenshot({
        path: job.png, type: 'png', omitBackground: !job.background,
        clip: { x: 0, y: 0, width: w, height: h },
      });
    }
  } finally {
    await browser.close();
  }
  console.log('rendered ' + jobs.length);
}

main().catch((e) => { console.error(e && e.stack ? e.stack : String(e)); process.exit(1); });
