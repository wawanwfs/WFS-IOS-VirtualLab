const {chromium}=require(process.env.WFS_PLAYWRIGHT);
const fs=require('fs');
const crypto=require('crypto');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto('http://localhost:8000');
  await page.waitForTimeout(1000);
  const frame=page.frames().find(f=>f.url().includes('vnc.html'));
  await frame.waitForFunction(()=>document.querySelector('#noVNC_status')?.textContent.includes('Connected'),null,{timeout:30000});
  await page.waitForTimeout(2000);
  let previous='';
  for(let i=0;i<40;i++){
   if(fs.existsSync('artifacts/stop-display-watch'))break;
   const shot=await frame.locator('canvas').screenshot();
   const hash=crypto.createHash('sha256').update(shot).digest('hex');
   if(hash!==previous){
    fs.writeFileSync('artifacts/latest-canvas.png',shot);
    await page.screenshot({path:'artifacts/latest-display.png',fullPage:true});
   }
   console.log(JSON.stringify({at:new Date().toISOString(),changed:hash!==previous,status:await page.locator('#status').textContent()}));
   previous=hash;
   await page.waitForTimeout(30000);
  }
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
