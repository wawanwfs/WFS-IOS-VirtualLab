const {chromium} = require(process.env.WFS_PLAYWRIGHT);
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto('http://localhost:8000');
 await page.waitForTimeout(1000);
 const frame=page.frames().find(frame=>frame.url().includes('vnc.html'));
 await frame.waitForFunction(()=>document.querySelector('#noVNC_status')?.textContent.includes('Connected'),null,{timeout:30000});
 await page.waitForTimeout(2000);
 await page.screenshot({path:process.argv[2]||'artifacts/dashboard-boot.png',fullPage:true});
 console.log(await page.locator('#status').textContent());
 console.log((await page.locator('#logs').textContent()).slice(-2000));
 await browser.close();
})().catch(error=>{console.error(error);process.exitCode=1});
