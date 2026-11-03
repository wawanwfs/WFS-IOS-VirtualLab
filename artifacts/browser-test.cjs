const {chromium} = require(process.env.WFS_PLAYWRIGHT);
const fs = require('fs');
(async () => {
 const browser = await chromium.launch({executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
 const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
 const errors = [];
 page.on('pageerror', error => errors.push(error.message));
 await page.goto('http://localhost:8000');
 await page.locator('#status').filter({hasText: 'STOPPED'}).waitFor();
 await page.locator('#screen').waitFor();
 await page.waitForFunction(() => !document.querySelector('#start').disabled);
 await page.locator('#seconds').fill('3600');
 await page.locator('#start').click();
 await page.waitForFunction(() => document.querySelector('#status').textContent === 'RUNNING');
 await page.waitForTimeout(5000);
 await page.screenshot({path: 'artifacts/dashboard-running.png', fullPage: true});
 const frame = page.frames().find(frame => frame.url().includes('vnc.html'));
 const vncStatus = frame ? await frame.locator('#noVNC_status').textContent() : 'iframe missing';
 const result = {errors, status: await page.locator('#status').textContent(), vncStatus, startDisabled: await page.locator('#start').isDisabled(), stopEnabled: await page.locator('#stop').isEnabled()};
 fs.writeFileSync('artifacts/browser-result.json', JSON.stringify(result, null, 2));
 console.log(JSON.stringify(result));
 await browser.close();
 if (errors.length || !result.stopEnabled || !vncStatus.includes('Connected')) process.exitCode = 1;
})().catch(error => {console.error(error);process.exitCode = 1});

