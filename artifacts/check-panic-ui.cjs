const {chromium} = require(process.env.WFS_PLAYWRIGHT);
const fs = require('fs');
(async () => {
 const browser = await chromium.launch({executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
 try {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/api/status', route => route.fulfill({json: {
   status: 'running', guest_status: 'failed', guest_error: 'panic(cpu 0): Ticket spinlock timeout',
   repository_present: true, userland_present: true, images_present: true,
   ready: true, missing: [], session_seconds_default: 3600,
  }}));
  await page.goto('http://localhost:8000');
  await page.waitForFunction(() => document.querySelector('#status').textContent === 'FAILED');
  const result = {fixture: true, status: await page.locator('#status').textContent(),
   hint: await page.locator('#hint').textContent(),
   startDisabled: await page.locator('#start').isDisabled(),
   stopEnabled: await page.locator('#stop').isEnabled(), errors};
  fs.writeFileSync('artifacts/browser-panic-ui.json', JSON.stringify(result, null, 2));
  await page.screenshot({path: 'artifacts/panic-ui-fixture.png', fullPage: true});
  console.log(JSON.stringify(result));
  if (errors.length || !result.startDisabled || !result.stopEnabled || !result.hint.includes('kernel error')) throw Error('Panic UI regression');
 } finally {await browser.close();}
})().catch(e => {console.error(e); process.exitCode = 1;});
